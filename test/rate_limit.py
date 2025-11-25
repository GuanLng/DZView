import asyncio
import time
from typing import Dict, Tuple

# Rate limiting: simple fixed window counters per IP and per domain.

_config_lock = asyncio.Lock()
_state_lock = asyncio.Lock()

_config = {
 "enabled": False,
 "window_seconds":60,
 "max_requests_per_ip":120, # None -> no limit
 "max_requests_per_domain":300, # None -> no limit
}

_ip_counts: Dict[Tuple[int, str], int] = {}
_domain_counts: Dict[Tuple[int, str], int] = {}


def _current_window_id(window_seconds: int) -> int:
 return int(time.time() // window_seconds)


async def get_rate_limit_config() -> dict:
 async with _config_lock:
 return dict(_config)


async def update_rate_limit_config(**kwargs) -> dict:
 async with _config_lock:
 for k, v in kwargs.items():
 if k in _config and v is not None:
 _config[k] = v
 return dict(_config)


async def _prune_old(window_id: int) -> None:
 # Remove previous window entries to keep memory bounded
 old_ip_keys = [k for k in _ip_counts if k[0] < window_id]
 for k in old_ip_keys:
 _ip_counts.pop(k, None)
 old_dom_keys = [k for k in _domain_counts if k[0] < window_id]
 for k in old_dom_keys:
 _domain_counts.pop(k, None)


async def check_and_increment(ip: str, domain: str) -> Tuple[bool, dict]:
 cfg = await get_rate_limit_config()
 if not cfg["enabled"]:
 return True, {
 "enabled": False,
 "limit_ip": None,
 "remaining_ip": None,
 "limit_domain": None,
 "remaining_domain": None,
 "reset": None,
 }

 window_id = _current_window_id(cfg["window_seconds"])
 reset_epoch = (window_id +1) * cfg["window_seconds"]

 async with _state_lock:
 await _prune_old(window_id)
 ip_key = (window_id, ip or "unknown")
 dom_key = (window_id, domain or "unknown")
 ip_count = _ip_counts.get(ip_key,0)
 dom_count = _domain_counts.get(dom_key,0)

 allowed = True
 if cfg["max_requests_per_ip"] is not None and ip_count >= cfg["max_requests_per_ip"]:
 allowed = False
 if cfg["max_requests_per_domain"] is not None and dom_count >= cfg["max_requests_per_domain"]:
 allowed = False

 if allowed:
 _ip_counts[ip_key] = ip_count +1
 _domain_counts[dom_key] = dom_count +1

 # Remaining values (after consuming this request if allowed)
 remaining_ip = None
 remaining_domain = None
 if cfg["max_requests_per_ip"] is not None:
 remaining_ip = max(cfg["max_requests_per_ip"] - (ip_count + (1 if allowed else0)),0)
 if cfg["max_requests_per_domain"] is not None:
 remaining_domain = max(cfg["max_requests_per_domain"] - (dom_count + (1 if allowed else0)),0)

 return allowed, {
 "enabled": True,
 "limit_ip": cfg["max_requests_per_ip"],
 "remaining_ip": remaining_ip,
 "limit_domain": cfg["max_requests_per_domain"],
 "remaining_domain": remaining_domain,
 "reset": reset_epoch,
 }


async def get_window_usage() -> dict:
 cfg = await get_rate_limit_config()
 if not cfg["enabled"]:
 return {"enabled": False}

 window_id = _current_window_id(cfg["window_seconds"])
 async with _state_lock:
 per_ip = {ip: c for (wid, ip), c in _ip_counts.items() if wid == window_id}
 per_domain = {dom: c for (wid, dom), c in _domain_counts.items() if wid == window_id}
 return {
 "enabled": True,
 "window_seconds": cfg["window_seconds"],
 "window_id": window_id,
 "max_requests_per_ip": cfg["max_requests_per_ip"],
 "max_requests_per_domain": cfg["max_requests_per_domain"],
 "reset_epoch": (window_id +1) * cfg["window_seconds"],
 "counts_ip": per_ip,
 "counts_domain": per_domain,
 }
