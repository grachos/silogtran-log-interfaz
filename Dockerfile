FROM python:3.13-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:${PORT:-8000} app.main:app"]
