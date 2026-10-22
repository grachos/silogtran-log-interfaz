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

## Firewall (AWS WAF) de Silogtran y login con navegador

Desde Render, `index.php?page=LoginPage` responde **HTTP 202** con `x-amzn-waf-action: challenge` y una página que exige JavaScript; un cliente HTTP no puede pasarla (confirmado 2026-10-22, también con cabeceras de Chrome).

Por eso, con `SILOGTRAN_LOGIN_MODE=auto` (por defecto), cuando aparece el desafío el login se hace con **Playwright** (Chromium headless): el navegador ejecuta el desafío como cualquier Chromium, completa usuario, contraseña y centro de costo, y se cierra. Sus cookies (incluida `aws-waf-token`) y su `User-Agent` pasan al cliente HTTP liviano, que hace el resto. Si el token vence, el siguiente acceso detecta el desafío y repite el login.

Límites deliberados: no se camufla la huella del navegador ni se resuelven CAPTCHAs. Si el WAF escala a CAPTCHA, la app responde `SILOGTRAN_WAF_CAPTCHA` y la solución es que Colombia Software / Elogia permita la IP del servicio.

- **Render:** requiere `runtime: docker` (el `Dockerfile` instala Chromium). El plan gratuito tiene 512 MB; Chromium solo vive durante el login.
- **GitHub Actions:** el flujo *Diagnostico Silogtran* (`workflow_dispatch`) corre el diagnóstico con los secretos `SILOGTRAN_USERNAME` y `SILOGTRAN_PASSWORD` del repositorio e imprime solo la estructura del formulario.
- **Local:** `python -m scripts.diagnostico` (con `python -m playwright install chromium`).

No probado aún contra el WAF real: la prueba `tests/test_browser_login.py` usa un servidor local que imita el desafío.
