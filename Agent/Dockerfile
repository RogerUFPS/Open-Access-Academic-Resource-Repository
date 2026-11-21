FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8000 \
    PORT_HEALTH=8000 \
    HEALTH_CHECK_PATH=/health

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY resources ./resources
COPY SKILL.md ./SKILL.md
COPY references ./references

RUN useradd --system --uid 10001 --home /app agent \
    && mkdir -p /app/data \
    && chown -R agent:agent /app

USER 10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; port=os.getenv('PORT_HEALTH', os.getenv('PORT', '8000')); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)"]

CMD ["sh", "-c", "exec uvicorn biblioteca_agent.api:app --host 0.0.0.0 --port ${PORT} --workers 1"]
