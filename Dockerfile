# Образ приложения: локальный запуск через venv не затрагивается.
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Логи сразу в docker compose logs (иначе буфер stdout).
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY recorder/ ./recorder/

# Слушать все интерфейсы; снаружи пробрасывайте любой свободный порт на 5000.
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

# Значения по умолчанию для контейнера (compose переопределит при необходимости).
ENV RECORDINGS_ROOT=/data/recordings
ENV STATE_DB_PATH=/data/state.sqlite3
ENV LOG_DIR=/data/logs

EXPOSE 5000

CMD ["python", "-m", "recorder"]
