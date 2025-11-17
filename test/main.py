from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
import logging
from pathlib import Path

# Support running as a module (test.main) or as a script from the test folder
try:
    from .proxy import router as proxy_router
    from .metrics import router as metrics_router
except ImportError:  # pragma: no cover - fallback for direct execution
    from proxy import router as proxy_router
    from metrics import router as metrics_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Py-Proxy",
    description="A FastAPI proxy application",
    version="0.1.0",
)

# Determine static dir relative to this file
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

# Mount static files only if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"Static files mounted successfully at {STATIC_DIR}")
else:
    logger.warning(f"Static directory not found at {STATIC_DIR}, skipping static file serving")

# Include routers
app.include_router(proxy_router)
app.include_router(metrics_router)

@app.get("/", response_class=HTMLResponse)
async def root():
    if STATIC_DIR.exists():
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
            <meta http-equiv=\"refresh\" content=\"0;url=/static/index.html\" />
            <title>Redirecting...</title>
            </head>
            <body>
            <p>Redirecting to <a href=\"/static/index.html\">proxy interface</a>...</p>
            </body>
            </html>
            """,
            status_code=200,
        )
    else:
        return HTMLResponse(
            content="""
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
            """,
            status_code=200,
        )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)