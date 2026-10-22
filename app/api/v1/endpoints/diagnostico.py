from fastapi import APIRouter, Depends, Request

from app.api.deps import require_token

router = APIRouter(prefix="/api/v1/diagnostico", tags=["diagnostico"])


@router.post("/formulario", dependencies=[Depends(require_token)])
async def formulario(request: Request):
    """Login + abre el formulario del log y devuelve su estructura (sin valores)."""
    return {"success": True, "data": await request.app.state.silogtran.diagnose_log_form()}
