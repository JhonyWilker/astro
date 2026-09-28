FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --system --uid 10001 --create-home astro \
    && mkdir -p /app/logs \
    && chown -R astro:astro /app

COPY --chown=astro:astro core ./core
COPY --chown=astro:astro tools ./tools
COPY --chown=astro:astro clients ./clients
COPY --chown=astro:astro config ./config

USER astro

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "core.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-max-size", "16384", "--ws-max-queue", "8"]
