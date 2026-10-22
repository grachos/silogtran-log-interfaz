"""Diagnostico del formulario del log desde la linea de comandos (o GitHub Actions).

Imprime solo estructura (nombres de controles, botones, pasos del login); nunca valores,
cookies ni credenciales.
"""
import asyncio
import json
import sys

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.services.silogtran_client import SilogtranClient


async def main() -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    client = SilogtranClient(settings)
    try:
        print(json.dumps(await client.diagnose_log_form(), ensure_ascii=False, indent=2))
        return 0
    except AppError as e:
        err = {"code": e.code, "message": e.message, "diagnostico": e.details, "pasos": client.trace}
        print(json.dumps(err, ensure_ascii=False, indent=2))
        return 1
    finally:
        await client.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
