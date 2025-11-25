from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import logging
import os
import socket
import time
from typing import List, Dict

# Support relative and absolute imports so the app works when started from the test folder or as a package
try:
    from .security import (
        extract_domain,
        is_domain_allowed,
        is_private_ip,
        compile_allowed_patterns,
    )
    from .metrics import add_up_bytes, add_down_bytes, record_request
except ImportError:  # pragma: no cover - fallback for direct execution
    from security import (
        extract_domain,
        is_domain_allowed,
        is_private_ip,
        compile_allowed_patterns,
    )
    from metrics import add_up_bytes, add_down_bytes, record_request

logger = logging.getLogger(__name__)

router = APIRouter()

UPSTREAM_TIMEOUT = 15.0
MAX_RESPONSE_SIZE = 100 * 1024 * 1024

# Allowed domains
ALLOWED_DOMAINS_ENV = os.getenv("ALLOWED_DOMAINS", "")
allowed_domains: List[str] = [d.strip() for d in ALLOWED_DOMAINS_ENV.split(",")] if ALLOWED_DOMAINS_ENV else []
allowed_patterns = compile_allowed_patterns(allowed_domains)

def _recompile_allowed():
    global allowed_patterns
    allowed_patterns = compile_allowed_patterns(allowed_domains)

def add_allowed_domain(pattern: str) -> bool:
    pattern = pattern.strip()
    if not pattern:
        return False
    if pattern in allowed_domains:
        return True
    try:
        compile_allowed_patterns([pattern]) # test compiling
    except Exception:
        return False
    allowed_domains.append(pattern)
    _recompile_allowed()
    return True

def remove_allowed_domain(pattern: str) -> bool:
    pattern = pattern.strip()
    if pattern in allowed_domains:
        allowed_domains.remove(pattern)
        _recompile_allowed()
        return True
    return False

# --------------------------- Rate limit state ---------------------------
RATE_LIMIT_ENABLED = False
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_IP = 120  # None means unlimited
RATE_LIMIT_MAX_DOMAIN = 300  # None means unlimited
_rate_ip_counts: Dict[str, int] = {}
_rate_domain_counts: Dict[str, int] = {}
_rate_window_id: int = int(time.time() // RATE_LIMIT_WINDOW_SECONDS)
_rate_reset_epoch: int = (_rate_window_id + 1) * RATE_LIMIT_WINDOW_SECONDS


def _current_window_id() -> int:
    return int(time.time() // RATE_LIMIT_WINDOW_SECONDS)


def _rotate_window_if_needed() -> None:
    global _rate_window_id, _rate_reset_epoch, _rate_ip_counts, _rate_domain_counts
    wid = _current_window_id()
    if wid != _rate_window_id:
        _rate_window_id = wid
        _rate_reset_epoch = (wid + 1) * RATE_LIMIT_WINDOW_SECONDS
        _rate_ip_counts = {}
        _rate_domain_counts = {}


def get_rate_limit_config() -> Dict[str, int | bool | None]:
    return {
        "enabled": RATE_LIMIT_ENABLED,
        "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
        "max_requests_per_ip": RATE_LIMIT_MAX_IP,
        "max_requests_per_domain": RATE_LIMIT_MAX_DOMAIN,
        "reset_epoch": _rate_reset_epoch,
    }


def update_rate_limit_config() -> Dict[str, int | bool | None]:
    global RATE_LIMIT_ENABLED, RATE_LIMIT_WINDOW_SECONDS, RATE_LIMIT_MAX_IP, RATE_LIMIT_MAX_DOMAIN, _rate_window_id, _rate_reset_epoch
    if "enabled" in kwargs:
        RATE_LIMIT_ENABLED = bool(kwargs["enabled"])
    if "window_seconds" in kwargs and isinstance(kwargs["window_seconds"], int) and kwargs["window_seconds"] > 0:
        RATE_LIMIT_WINDOW_SECONDS = kwargs["window_seconds"]
    if "max_requests_per_ip" in kwargs:
        RATE_LIMIT_MAX_IP = kwargs["max_requests_per_ip"]
    if "max_requests_per_domain" in kwargs:
        RATE_LIMIT_MAX_DOMAIN = kwargs["max_requests_per_domain"]
    # Force rotate to apply new window size immediately
    _rate_window_id = _current_window_id()
    _rate_reset_epoch = (_rate_window_id + 1) * RATE_LIMIT_WINDOW_SECONDS
    return get_rate_limit_config()


def get_window_usage() -> Dict[str, Dict[str, int] | int | bool]:
    _rotate_window_if_needed()
    if not RATE_LIMIT_ENABLED:
        return {"enabled": False}
    return {
        "enabled": True,
        "window_id": _rate_window_id,
        "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
        "reset_epoch": _rate_reset_epoch,
        "counts_ip": dict(_rate_ip_counts),
        "counts_domain": dict(_rate_domain_counts),
        "max_requests_per_ip": RATE_LIMIT_MAX_IP,
        "max_requests_per_domain": RATE_LIMIT_MAX_DOMAIN,
    }


def check_and_increment(ip: str, domain: str) -> (bool, Dict[str, int | bool | None]):
    _rotate_window_if_needed()
    if not RATE_LIMIT_ENABLED:
        return True, {"enabled": False, "limit_ip": None, "remaining_ip": None, "limit_domain": None, "remaining_domain": None, "reset": None}
    ip_key = ip or "unknown"
    dom_key = domain or "unknown"
    ip_count = _rate_ip_counts.get(ip_key, 0)
    dom_count = _rate_domain_counts.get(dom_key, 0)
    allowed = True
    if RATE_LIMIT_MAX_IP is not None and ip_count >= RATE_LIMIT_MAX_IP:
        allowed = False
    if RATE_LIMIT_MAX_DOMAIN is not None and dom_count >= RATE_LIMIT_MAX_DOMAIN:
        allowed = False
    if allowed:
        _rate_ip_counts[ip_key] = ip_count + 1
        _rate_domain_counts[dom_key] = dom_count + 1
        remaining_ip = None
        remaining_domain = None
        if RATE_LIMIT_MAX_IP is not None:
            remaining_ip = max(RATE_LIMIT_MAX_IP - (ip_count + (1 if allowed else 0)), 0)
        if RATE_LIMIT_MAX_DOMAIN is not None:
            remaining_domain = max(RATE_LIMIT_MAX_DOMAIN - (dom_count + (1 if allowed else 0)), 0)
        meta = {
            "enabled": True,
            "limit_ip": RATE_LIMIT_MAX_IP,
            "remaining_ip": remaining_ip,
            "limit_domain": RATE_LIMIT_MAX_DOMAIN,
            "remaining_domain": remaining_domain,
            "reset": _rate_reset_epoch,
        }
        return allowed, meta

# -----------------------------------------------------------------------

def _sanitize_headers(src_headers: Dict[str, str]) -> Dict[str, str]:
    h = dict(src_headers)
    for key in (
        "content-length",
        "Content-Length",
        "transfer-encoding",
        "Transfer-Encoding",
        "connection",
        "Connection",
        "content-encoding",
        "Content-Encoding",
        "etag",
        "ETag",
    ):
        h.pop(key, None)
    return h


@router.api_route("/proxy/{target:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_handler(request: Request, target: str) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Proxy request from {client_ip}: {request.method} /proxy/{target}")

    # Build target URL
    if not target.startswith(("http://", "https://")):
        target_url = f"https://{target}"
    else:
        target_url = target

    # Allowlist check
    domain = extract_domain(target_url)
    if domain is None:
        logger.warning(f"Invalid target URL: {target_url}")
        raise HTTPException(status_code=400, detail="Invalid target URL")

    if not is_domain_allowed(domain, allowed_patterns):
        logger.warning(f"Domain not allowed: {domain}")
        raise HTTPException(status_code=403, detail="Domain not allowed")

    # Rate limit check
    allowed_rl, rl_meta = check_and_increment(client_ip, domain)
    if not allowed_rl:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # DNS and private IP block
    try:
        ip = socket.gethostbyname(domain)
        logger.info(f"Resolved {domain} to {ip}")
        if is_private_ip(ip):
            logger.warning(f"Blocked access to private IP: {ip}")
            raise HTTPException(status_code=403, detail="Access to private IP ranges is forbidden")
    except socket.gaierror:
        logger.error(f"Cannot resolve hostname {domain}")
        raise HTTPException(status_code=502, detail="Name or service not known")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error during IP resolution: {e}")

    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)

    logger.info(f"Forwarding {method} request to {target_url}")

    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        try:
            up_len = 0
            if method in ("POST", "PUT", "PATCH"):
                body = await request.body()
                up_len = len(body)
                await add_up_bytes(up_len)
                httpx_response = await client.request(
                    method=method,
                    url=target_url,
                    headers=headers,
                    content=body if body else None,
                )
            else:
                httpx_response = await client.request(
                    method=method, url=target_url, headers=headers
                )

            logger.info(
                f"Received response from {target_url}: {httpx_response.status_code}"
            )

            # Check Content-Length header if available
            content_length = httpx_response.headers.get("content-length")
            if content_length:
                try:
                    length = int(content_length)
                    if length > MAX_RESPONSE_SIZE:
                        logger.warning(f"Response too large: {length} bytes")
                        raise HTTPException(status_code=413, detail="Payload too large")
                except ValueError:
                    pass

            # Determine if response is text-based
            content_type = httpx_response.headers.get("content-type", "").lower()
            is_text_content = (
                "text" in content_type
                or "json" in content_type
                or "xml" in content_type
                or "javascript" in content_type
                or "html" in content_type
                or content_type == ""
            )

            if is_text_content:
                down_len = len(httpx_response.content)
                await add_down_bytes(down_len)
                await record_request(domain, method, up_len, down_len)

                resp = Response(
                    content=httpx_response.content,
                    status_code=httpx_response.status_code,
                    headers=_sanitize_headers(httpx_response.headers),
                    media_type=content_type or "text/plain",
                )
                if rl_meta.get('enabled'):
                    resp.headers['X-RateLimit-Limit-IP'] = str(rl_meta.get('limit_ip'))
                    resp.headers['X-RateLimit-Remaining-IP'] = str(rl_meta.get('remaining_ip'))
                    resp.headers['X-RateLimit-Limit-Domain'] = str(rl_meta.get('limit_domain'))
                    resp.headers['X-RateLimit-Remaining-Domain'] = str(rl_meta.get('remaining_domain'))
                    resp.headers['X-RateLimit-Reset'] = str(rl_meta.get('reset'))
                return resp
            else:
                down_len_local = [0]

                async def stream_generator():
                    async for chunk in httpx_response.aiter_bytes():
                        clen = len(chunk)
                        await add_down_bytes(clen)
                        down_len_local[0] += clen
                        yield chunk

                response = StreamingResponse(
                    stream_generator(),
                    status_code=httpx_response.status_code,
                    headers=_sanitize_headers(httpx_response.headers),
                    media_type=content_type,
                )

                async def finalize():
                    await record_request(domain, method, up_len, down_len_local[0])
                response.background = finalize # FastAPI will run coroutine
                if rl_meta.get('enabled'):
                    response.headers['X-RateLimit-Limit-IP'] = str(rl_meta.get('limit_ip'))
                    response.headers['X-RateLimit-Remaining-IP'] = str(rl_meta.get('remaining_ip'))
                    response.headers['X-RateLimit-Limit-Domain'] = str(rl_meta.get('limit_domain'))
                    response.headers['X-RateLimit-Remaining-Domain'] = str(rl_meta.get('remaining_domain'))
                    response.headers['X-RateLimit-Reset'] = str(rl_meta.get('reset'))
                return response

        except httpx.TimeoutException as e:
            logger.error(f"Upstream timeout for {target_url}: {e}")
            raise HTTPException(status_code=504, detail="Upstream timeout")
        except httpx.RequestError as e:
            logger.error(f"Proxy error for {target_url}: {e}")
            if "Name or service not known" in str(e) or "getaddrinfo failed" in str(e):
                raise HTTPException(status_code=502, detail="Name or service not known")
            return Response(
                content=f"Proxy error: {str(e)}",
                status_code=500,
                media_type="text/plain",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error for {target_url}: {e}")
            return Response(
                content=f"Unexpected error: {str(e)}",
                status_code=500,
                media_type="text/plain",
            )
