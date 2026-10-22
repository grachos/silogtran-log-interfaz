FROM python:3.13-slim-bookworm
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY requirements.txt .
# Chromium (solo headless shell, el mas liviano) para pasar el desafio JavaScript del WAF en el login.
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*
COPY app ./app
COPY scripts ./scripts
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 1 -t 180 -b 0.0.0.0:${PORT:-8000} app.main:app"]
