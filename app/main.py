import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.endpoints import diagnostico, health
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.services.rate_limiter import RateLimiter
from app.services.silogtran_client import SilogtranClient

log = logging.getLogger("app")
STATIC = Path(__file__).parent / "static"


def error_body(code: str, message: str, request: Request, details: dict | None = None) -> dict:
    err = {"code": code, "message": message, "request_id": getattr(request.state, "request_id", "")}
    if details:
        err["diagnostico"] = details
    return {"success": False, "error": err}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.silogtran = SilogtranClient(settings)
    task = asyncio.create_task(app.state.silogtran.keepalive_loop())
    yield
    task.cancel()
    await app.state.silogtran.aclose()


app = FastAPI(title="Silogtran Log Interfaz", version="0.1.0-diagnostico", lifespan=lifespan)
app.include_router(health.router)
app.include_router(diagnostico.router)


@app.middleware("http")
async def request_id_mw(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex[:8]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(error_body(exc.code, exc.message, request, exc.details), status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("error no controlado")
    return JSONResponse(error_body("INTERNAL_ERROR", "Error interno.", request), status_code=500)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC / "index.html")
