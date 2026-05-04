# Docker: шпаргалка команд

Все команды выполняй из каталога, где лежит **`docker-compose.yml`** (корень проекта).

На Synology, если без `sudo` ошибка `permission denied` к Docker — везде добавь **`sudo`** перед `docker`.

---

## Первый запуск

```bash
cd /path/to/ffmpeg-stream-rec
cp .env.example .env
# Отредактируй .env: SECRET_KEY обязателен; при необходимости HOST_PORT

mkdir -p docker-data

docker compose build
docker compose up -d
```

---

## Обновление кода (после git pull или распаковки архива)

```bash
cd /path/to/ffmpeg-stream-rec
docker compose down
docker compose build
docker compose up -d
```

Пересборка без кэша (если подозреваешь залипший слой образа):

```bash
docker compose build --no-cache
docker compose up -d
```

---

## Статус и логи

```bash
docker compose ps
docker compose logs recorder --tail 80
docker compose logs -f recorder
```

Остановка контейнера (данные в **`docker-data/`** на диске остаются):

```bash
docker compose down
```

---

## Проверка с хоста

Интерфейс (порт по умолчанию **8080**, или значение **`HOST_PORT`** из `.env`):

- `http://127.0.0.1:8080`
- с другого ПК: `http://IP-ХОСТА:8080`

JSON статусов (размер файла, хвост stderr FFmpeg):

```bash
curl -s http://127.0.0.1:8080/record/status | head -c 2000
```

Файлы записей на диске хоста:

```bash
ls -la docker-data
ls -la docker-data/recordings
```

---

## Команды внутри контейнера

Проверка, что FFmpeg из контейнера достучался до потока (**URL без пробела в конце и без лишнего пробела перед `"`**):

```bash
docker compose exec recorder ls -la /data/recordings
docker compose exec recorder ffmpeg -hide_banner -loglevel info -i "https://ПОДСТАВЬ_URL/index.m3u8" -t 15 -c copy -f null -
```

---

## Локальные тесты (без Docker, нужен venv)

```bash
cd /path/to/ffmpeg-stream-rec
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

---

## Куда что пишется

| На хосте (рядом с compose) | В контейнере |
|----------------------------|--------------|
| `docker-data/recordings/`  | `/data/recordings/` |
| `docker-data/state.sqlite3` | `/data/state.sqlite3` |
| `docker-data/logs/`       | `/data/logs/` |

Переменные **`RECORDINGS_ROOT` / `STATE_DB_PATH` / `LOG_DIR`** в `.env` для Docker **не задают** эти пути — их фиксирует **`docker-compose.yml`**.
