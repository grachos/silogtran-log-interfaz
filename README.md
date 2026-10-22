# Silogtran Log Interfaz

Consulta el **Log de la Interfaz** de Silogtran (PRADO) y reenvía el JSON de "Parámetros de entrada" de cada registro a la API de AWS, verificando después que SAP lo guardó.

## Estado: versión diagnóstica (fase 1)

Los nombres reales de los controles PRADO no se conocen, así que esta primera versión **solo** hace:

- login + selección del centro de costo (`SILOGTRAN_COST_CENTER`) con sesión persistente y renovación cada `SILOGTRAN_KEEPALIVE_SECONDS`;
- `POST /api/v1/diagnostico/formulario` (Bearer `API_TOKEN`): abre `BuscarLogInterfaz` y devuelve la estructura del formulario (controles, ocultos, botones, detección por etiqueta). **No devuelve valores** ni secretos;
- pantalla `/` que invoca ese endpoint; `GET /health`.

**Pendiente (fases siguientes):** búsqueda, lectura de la grilla, envío a AWS, verificación en SAP, trabajos en segundo plano. Se completan con el resultado del diagnóstico (o con HTML guardado / HAR de una búsqueda real). Nada de esto está probado contra Silogtran real: las pruebas usan mocks y los pasos de login/centro de costo son suposiciones a confirmar.

## Uso local

```bash
pip install -r requirements.txt
cp .env.example .env   # completar SILOGTRAN_USERNAME, SILOGTRAN_PASSWORD, API_TOKEN
uvicorn app.main:app --reload
python -m pytest
curl -X POST localhost:8000/api/v1/diagnostico/formulario -H "Authorization: Bearer $API_TOKEN"
```

## Render

`render.yaml` define un único worker (`gunicorn -k uvicorn.workers.UvicornWorker -w 1`). Completar en Render los secretos `SILOGTRAN_USERNAME`, `SILOGTRAN_PASSWORD`, `TARGET_API_KEY`. Si el repo se conectó por URL pública, los `push` no despliegan solos: usar *Manual Deploy*. En plan gratuito el servicio se duerme tras 15 min (la renovación de sesión también), el primer acceso tarda 30–60 s y la memoria se pierde en cada reinicio.

## Errores

`{"success": false, "error": {"code", "message", "request_id", "diagnostico"?}}` (el bloque `diagnostico` solo en fallos de login: título, formularios y tipos/nombres de controles de la página recibida, sin valores) — 401 token, 502 formato inesperado, 503 sesión no disponible, 504 timeout.
