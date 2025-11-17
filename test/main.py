from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx
import ipaddress
import re
import os
import logging
from typing import AsyncGenerator, List, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Py-Proxy",
    description="A FastAPI proxy application",
    version="0.1.0"
)

# Mount static files only if directory exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    logger.info("Static files mounted successfully")
else:
    logger.warning("Static directory not found, skipping static file serving")

# Get allowed domains list
ALLOWED_DOMAINS_ENV = os.getenv("ALLOWED_DOMAINS", "")
allowed_domains: List[str] = []
if ALLOWED_DOMAINS_ENV:
    allowed_domains = [domain.strip() for domain in ALLOWED_DOMAINS_ENV.split(",")]

# Compile regex patterns
allowed_patterns = [re.compile(pattern) for pattern in allowed_domains]

# Private IP ranges
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128")
]

# Constants
UPSTREAM_TIMEOUT = 15.0
MAX_RESPONSE_SIZE = 100 * 1024 * 1024  # 100 MB

def is_private_ip(ip: str) -> bool:
    """Check if IP is in private range"""
    try:
        ip_obj = ipaddress.ip_address(ip)
        for network in PRIVATE_IP_RANGES:
            if ip_obj in network:
                return True
        return False
    except ValueError:
        # If not a valid IP address, consider it not private
        return False

def is_domain_allowed(domain: str) -> bool:
    """Check if domain is in allow list"""
    if not allowed_patterns:
        # If no allow list set, allow all domains
        return True
    
    for pattern in allowed_patterns:
        if pattern.match(domain):
            return True
    return False

def extract_domain(url: str) -> Optional[str]:
    """Extract domain from URL"""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.hostname
    except Exception:
        return None

@app.get("/", response_class=HTMLResponse)
async def root():
    # 如果有static目录，重定向到静态页面
    if os.path.exists("static"):
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <meta http-equiv="refresh" content="0;url=/static/index.html" />
            <title>Redirecting...</title>
        </head>
        <body>
            <p>Redirecting to <a href="/static/index.html">proxy interface</a>...</p>
        </body>
        </html>
        """, status_code=200)
    else:
        # 如果没有static目录，显示简单的根页面
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Py-Proxy</title>
        </head>
        <body>
            <h1>Py-Proxy</h1>
            <p>Proxy service is running.</p>
            <p>To use the web interface, please create a <code>static</code> directory with an <code>index.html</code> file.</p>
        </body>
        </html>
        """, status_code=200)

@app.api_route("/proxy/{target:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_handler(request: Request, target: str) -> Response:
    # Log the incoming request
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Proxy request from {client_ip}: {request.method} /proxy/{target}")
    
    # Construct target URL
    if not target.startswith(("http://", "https://")):
        target_url = f"https://{target}"
    else:
        target_url = target
    
    # Check if domain is allowed
    domain = extract_domain(target_url)
    if domain is None:
        logger.warning(f"Invalid target URL: {target_url}")
        raise HTTPException(status_code=400, detail="Invalid target URL")
    
    if not is_domain_allowed(domain):
        logger.warning(f"Domain not allowed: {domain}")
        raise HTTPException(status_code=403, detail="Domain not allowed")
    
    # Resolve target host IP and check if it's private IP
    try:
        import socket
        hostname = domain
        ip = socket.gethostbyname(hostname)
        logger.info(f"Resolved {hostname} to {ip}")
        if is_private_ip(ip):
            logger.warning(f"Blocked access to private IP: {ip}")
            raise HTTPException(status_code=403, detail="Access to private IP ranges is forbidden")
    except socket.gaierror as e:
        logger.error(f"Cannot resolve hostname {hostname}: {e}")
        raise HTTPException(status_code=502, detail="Name or service not known")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error during IP resolution: {e}")
        # If resolution fails, continue processing and let httpx handle errors
    
    # Prepare forwarding request parameters
    method = request.method
    headers = dict(request.headers)
    
    # Remove headers that might affect proxy behavior
    headers.pop("host", None)
    
    # Log the outgoing request
    logger.info(f"Forwarding {method} request to {target_url}")
    
    # Use httpx.AsyncClient to forward request
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        try:
            # For methods with body, read and send body
            if method in ("POST", "PUT", "PATCH"):
                body = await request.body()
                httpx_response = await client.request(
                    method=method,
                    url=target_url,
                    headers=headers,
                    content=body if len(body) > 0 else None
                )
            else:
                # For methods without body, send directly
                httpx_response = await client.request(
                    method=method,
                    url=target_url,
                    headers=headers
                )
            
            # Log the response
            logger.info(f"Received response from {target_url}: {httpx_response.status_code}")
            
            # Check Content-Length header if available
            content_length = httpx_response.headers.get("content-length")
            if content_length:
                try:
                    length = int(content_length)
                    if length > MAX_RESPONSE_SIZE:
                        logger.warning(f"Response too large: {length} bytes")
                        raise HTTPException(status_code=413, detail="Payload too large")
                except ValueError:
                    pass  # Ignore if content-length is not a valid integer
            
            # Determine if response is text-based
            content_type = httpx_response.headers.get("content-type", "").lower()
            is_text_content = (
                "text" in content_type or 
                "json" in content_type or 
                "xml" in content_type or 
                "javascript" in content_type or 
                "html" in content_type or
                content_type == ""
            )
            
            # For text content, forward bytes and clean headers
            if is_text_content:
                content_bytes = httpx_response.content

                # Prepare response headers and remove hop-by-hop or invalid enc headers
                resp_headers = dict(httpx_response.headers)
                for h in [
                    'content-length','Content-Length',
                    'transfer-encoding','Transfer-Encoding',
                    'connection','Connection',
                    'content-encoding','Content-Encoding',
                    'etag','ETag'
                ]:
                    resp_headers.pop(h, None)

                return Response(
                    content=content_bytes,
                    status_code=httpx_response.status_code,
                    headers=resp_headers,
                    media_type=content_type or "text/plain"
                )
            else:
                # For binary content, stream it
                async def stream_generator():
                    async for chunk in httpx_response.aiter_bytes():
                        yield chunk
                
                # Remove hop-by-hop and encoding headers for streaming responses as well
                resp_headers = dict(httpx_response.headers)
                for h in [
                    'content-length','Content-Length',
                    'transfer-encoding','Transfer-Encoding',
                    'connection','Connection',
                    'content-encoding','Content-Encoding',
                    'etag','ETag'
                ]:
                    resp_headers.pop(h, None)
 
                return StreamingResponse(
                    stream_generator(),
                    status_code=httpx_response.status_code,
                    headers=resp_headers,
                    media_type=content_type
                )
                
        except httpx.TimeoutException as e:
            logger.error(f"Upstream timeout for {target_url}: {e}")
            raise HTTPException(status_code=504, detail="Upstream timeout")
        except httpx.RequestError as e:
            logger.error(f"Proxy error for {target_url}: {e}")
            # Check if it's a DNS resolution error
            if "Name or service not known" in str(e) or "getaddrinfo failed" in str(e):
                raise HTTPException(status_code=502, detail="Name or service not known")
            return Response(
                content=f"Proxy error: {str(e)}",
                status_code=500,
                media_type="text/plain"
            )
        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as e:
            logger.error(f"Unexpected error for {target_url}: {e}")
            return Response(
                content=f"Unexpected error: {str(e)}",
                status_code=500,
                media_type="text/plain"
            )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)