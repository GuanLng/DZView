import os
from fastapi import Header, HTTPException, status

ADMIN_KEY_ENV = "ADMIN_API_KEY"

async def require_admin(x_api_key: str = Header(None)):
    expected = os.getenv(ADMIN_KEY_ENV)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API key not configured (set ADMIN_API_KEY environment variable).",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header.",
        )
    return True
