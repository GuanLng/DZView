import asyncio
import time
from collections import deque, defaultdict
from typing import Dict, Deque, Tuple
from fastapi import APIRouter

router = APIRouter()

# Global traffic counters protected by an asyncio lock
_traffic_lock = asyncio.Lock()
_total_up_bytes: int =0
_total_down_bytes: int =0
_total_requests: int =0
_start_time: float = time.time()
_method_counts: Dict[str, int] = defaultdict(int)
_domain_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {
 'requests':0,
 'up_bytes':0,
 'down_bytes':0
})
# Recent activity for rate computation (timestamp, up, down)
_recent: Deque[Tuple[float, int, int]] = deque()
_MAX_WINDOW_SECONDS =60

async def add_up_bytes(n: int) -> None:
    global _total_up_bytes
    if n and n >0:
        async with _traffic_lock:
            _total_up_bytes += n
            _recent.append((time.time(), n,0))
            _trim_recent_locked()

async def add_down_bytes(n: int) -> None:
    global _total_down_bytes
    if n and n >0:
        async with _traffic_lock:
            _total_down_bytes += n
            _recent.append((time.time(),0, n))
            _trim_recent_locked()

async def record_request(domain: str, method: str, up_bytes: int, down_bytes: int) -> None:
    global _total_requests
    async with _traffic_lock:
        _total_requests +=1
        _method_counts[method] +=1
        stats = _domain_stats[domain]
        stats['requests'] +=1
        stats['up_bytes'] += up_bytes
        stats['down_bytes'] += down_bytes
    # Recent already appended via add_*; nothing extra needed

def _trim_recent_locked() -> None:
    cutoff = time.time() - _MAX_WINDOW_SECONDS
    while _recent and _recent[0][0] < cutoff:
        _recent.popleft()

def _compute_rates_locked() -> Dict[str, float]:
    if not _recent:
        return {'up_bps':0.0, 'down_bps':0.0}
    now = time.time()
    window_start = _recent[0][0]
    elapsed = max(0.001, now - window_start)
    up = sum(r[1] for r in _recent)
    down = sum(r[2] for r in _recent)
    return {
        'up_bps': up / elapsed,
        'down_bps': down / elapsed
    }

async def get_totals() -> dict:
    async with _traffic_lock:
        _trim_recent_locked()
        rates = _compute_rates_locked()
        uptime = time.time() - _start_time
        return {
            'total_up_bytes': _total_up_bytes,
            'total_down_bytes': _total_down_bytes,
            'total_bytes': _total_up_bytes + _total_down_bytes,
            'total_requests': _total_requests,
            'uptime_seconds': uptime,
            'method_counts': dict(_method_counts),
            'domain_stats': _domain_stats, # already plain ints
            'rates': rates,
            'window_seconds': _MAX_WINDOW_SECONDS
        }

@router.get('/metrics/traffic')
async def get_traffic_metrics():
    return await get_totals()

@router.post('/metrics/traffic/reset')
async def reset_traffic_metrics():
    global _total_up_bytes, _total_down_bytes, _total_requests
    async with _traffic_lock:
        _total_up_bytes =0
        _total_down_bytes =0
        _total_requests =0
        _method_counts.clear()
        _domain_stats.clear()
        _recent.clear()
        # keep start time
    return {'ok': True}
