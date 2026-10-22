import hashlib

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.exceptions import RateLimited, Unauthorized
from app.core.security import token_matches

bearer = HTTPBearer(auto_error=False)


async def require_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    if creds is None or not token_matches(creds.credentials, settings.api_token):
        raise Unauthorized("Token ausente o invalido.")
    key = hashlib.sha256(creds.credentials.encode()).hexdigest()
    if not request.app.state.rate_limiter.allow(key):
        raise RateLimited("Demasiadas solicitudes; intente en un minuto.")
    return key
