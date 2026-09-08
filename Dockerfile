FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Cloud Run sends traffic to $PORT and scales this container to zero when idle.
ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn src.web.app:app --host 0.0.0.0 --port ${PORT}
