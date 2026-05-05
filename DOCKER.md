# Docker: шпаргалка команд

Все команды выполняй из каталога, где лежит **`docker-compose.yml`** (корень проекта).

**Synology / нет доступа к сокету Docker без root:** используй **`sudo`** у **каждой** команды `docker` и `docker compose` (ниже есть готовые блоки). Если в одном месте забудешь `sudo`, compose может подключиться к «чужому» контексту или выдать `permission denied`.

---

## Первый запуск

**Linux / Mac (пользователь в группе `docker`):**

```bash
cd /path/to/ffmpeg-stream-rec
cp .env.example .env
# Отредактируй .env: SECRET_KEY обязателен; при необходимости HOST_PORT

mkdir -p docker-data

docker compose build
docker compose up -d
```

**Почему так настроено compose (и это не трогает Jupyter):**

- **`init: true`** — в контейнере PID 1 — это *tini*: корректная доставка **SIGTERM** при `docker stop` и уменьшение проблем с дочерними процессами FFmpeg (зомби). Локальный ноутбук поднимает **`recorder.dev_server_main`**, не `python -m recorder`.
- **`healthcheck`** — проверка `GET /` изнутри контейнера; в `docker compose ps` видно `healthy`. На работу Jupyter не влияет.
- Образ задаёт **`PYTHONUNBUFFERED=1`**, чтобы строки логов сразу попадали в `docker compose logs`.

**Synology (SSH), тот же сценарий с `sudo`:**

```bash
cd /volume1/docker/ffmpeg-stream-rec-feature-docker
cp .env.example .env
# SECRET_KEY, при необходимости HOST_PORT

sudo mkdir -p docker-data

sudo docker compose build
sudo docker compose up -d
```

---

## Обновление кода (после git pull или распаковки архива)

```bash
cd /path/to/ffmpeg-stream-rec
docker compose down
docker compose build
docker compose up -d
```

**С `sudo` (NAS):**

```bash
cd /volume1/docker/ffmpeg-stream-rec-feature-docker
sudo docker compose down
sudo docker compose build
sudo docker compose up -d
```

Пересборка без кэша (если подозреваешь залипший слой образа):

```bash
docker compose build --no-cache
docker compose up -d
```

**С `sudo`:**

```bash
sudo docker compose build --no-cache
sudo docker compose up -d
```

---

## Статус и логи

Без `sudo` (если пользователь в группе `docker`):

```bash
docker compose ps
docker compose logs recorder --tail 30
docker compose logs recorder --tail 80
docker compose logs -f recorder
```

На Synology чаще нужен **`sudo`**:

```bash
sudo docker compose ps
sudo docker compose logs recorder --tail 30
sudo docker compose logs recorder --tail 80
sudo docker compose logs -f recorder
```

Остановка контейнера (данные в **`docker-data/`** на диске остаются):

```bash
docker compose down
```

```bash
sudo docker compose down
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

**С `sudo`:**

```bash
sudo docker compose exec recorder ls -la /data/recordings
sudo docker compose exec recorder ffmpeg -hide_banner -loglevel info -i "https://ПОДСТАВЬ_URL/index.m3u8" -t 15 -c copy -f null -
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

---

## Автопроверка в репозитории

В GitHub на push/PR workflow **Docker build** выполняет:

1. `docker compose config`
2. `docker compose build`
3. **Smoke:** из `.env.example` собирается временный `.env`, `compose up`, несколько запросов к `http://127.0.0.1:8080/` и `/record/status`, затем `compose down`.

Зелёная галочка = образ собирается и приложение **поднимается** в контейнере. Это **не** проверяет твой NAS и **не** гоняет реальный HLS/FFmpeg-запись.

### Что можно добавить позже (по желанию)

| Идея | Зачем |
|------|--------|
| **Hadolint / Trivy** по Dockerfile | стиль слоёв, известные CVE базового образа |
| **Отдельный nightly job** с `ffmpeg -i` на публичный тестовый HLS внутри `exec` | ловить сетевые/SSL регрессии в образе |
| **`docker compose up` + pytest с `network_mode: host`** | сложнее в CI, обычно избыточно для этого проекта |

Локально без Docker daemon достаточно **`pytest`**; с Docker — ручной сценарий из раздела «Первый запуск» + запись из UI.
