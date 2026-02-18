from __future__ import annotations

import hmac
from fastapi import HTTPException, status


def require_api_key(x_api_key: str | None, required_key: str) -> None:
    if not required_key:
        return  # disabled
    if not x_api_key or not hmac.compare_digest(x_api_key, required_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
