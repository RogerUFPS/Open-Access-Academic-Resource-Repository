FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY resources ./resources
COPY config ./config

RUN useradd --system --uid 10001 --home /app agent \
    && mkdir -p /app/data \
    && chown -R agent:agent /app

USER 10001

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn biblioteca_agent.api:app --host 0.0.0.0 --port ${PORT}"]
