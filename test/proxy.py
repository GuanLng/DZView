from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import logging
import os
import socket
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
            up_len =0
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

                return Response(
                    content=httpx_response.content,
                    status_code=httpx_response.status_code,
                    headers=_sanitize_headers(httpx_response.headers),
                    media_type=content_type or "text/plain",
                )
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
                # Attach background task to record metrics after streaming completes
                async def finalize():
                    await record_request(domain, method, up_len, down_len_local[0])
                response.background = finalize # FastAPI will run coroutine
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
