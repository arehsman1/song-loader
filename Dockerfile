FROM python:3.12-slim-bookworm

# Install FFmpeg (optional but useful if a real provider is added later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

USER appuser

# Persistent data volume expected at /app/data
ENV DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os,sys; sys.exit(0 if os.getenv('TELEGRAM_BOT_TOKEN') else 1)"

CMD ["python", "bot.py"]
