# syntax=docker/dockerfile:1
# Multi-stage: build wheels, then minimal runtime image with non-root user.

FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir -r requirements.txt -w /wheels

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY requirements.txt .
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --find-links=/wheels -r requirements.txt && rm -rf /wheels

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

RUN chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
