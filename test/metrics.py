import asyncio
from fastapi import APIRouter

router = APIRouter()

# Global traffic counters protected by an asyncio lock
_traffic_lock = asyncio.Lock()
_total_up_bytes: int =0
_total_down_bytes: int =0


async def add_up_bytes(n: int) -> None:
    global _total_up_bytes
    if n and n >0:
        async with _traffic_lock:
            _total_up_bytes += n


async def add_down_bytes(n: int) -> None:
    global _total_down_bytes
    if n and n >0:
        async with _traffic_lock:
            _total_down_bytes += n


async def get_totals() -> dict:
    async with _traffic_lock:
        return {
            "total_up_bytes": _total_up_bytes,
            "total_down_bytes": _total_down_bytes,
            "total_bytes": _total_up_bytes + _total_down_bytes,
        }


@router.get("/metrics/traffic")
async def get_traffic_metrics():
    return await get_totals()


@router.post("/metrics/traffic/reset")
async def reset_traffic_metrics():
    global _total_up_bytes, _total_down_bytes
    async with _traffic_lock:
        _total_up_bytes =0
        _total_down_bytes =0
    return {"ok": True}
