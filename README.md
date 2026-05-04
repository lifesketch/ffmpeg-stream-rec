# ffmpeg-stream-rec

Веб‑приложение на Flask для записи HLS (`.m3u8`) в MP4 через FFmpeg по [техническому заданию](docs/business-requirements/flask_ffmpeg_recorder_spec.md).

## Что такое HLS

**HLS** расшифровывается как **HTTP Live Streaming** — способ отдавать видео и аудио по обычному HTTPS отдельными фрагментами. Обычно это плейлист в формате **`.m3u8`** и сегменты (например `.ts` или fMP4); плеер подкачивает следующие куски по мере воспроизведения.

В этом проекте **«запись HLS»** означает: вы указываете URL потока с **`.m3u8`**, а FFmpeg читает поток и сохраняет результат в один файл **MP4**.

## Требования

- Python 3.11+
- Установленные в системе `ffmpeg` и `ffprobe` (`ffmpeg -version`)

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Каталоги `recordings/`, `data/`, `logs/` создаются при старте приложения.

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

Тесты используют временные каталоги и не запускают реальный FFmpeg: процесс записи и shutdown-hooks замоканы в [`tests/conftest.py`](tests/conftest.py).

## Запуск

```bash
source .venv/bin/activate
python -m recorder
```

Открой в браузере: http://127.0.0.1:5000

Порт и хост задаются переменными **`FLASK_RUN_HOST`** и **`FLASK_RUN_PORT`** (см. `recorder/__main__.py`). Если **5000 уже занят** (часто бывает на macOS из‑за AirPlay Receiver или другого сервиса), запусти на другом порту:

```bash
FLASK_RUN_PORT=8080 python -m recorder
```

Тогда адрес будет http://127.0.0.1:8080 .

**Docker (кратко):** внутри контейнера по умолчанию порт **5000**; на хосте пробрасывается любой свободный (см. раздел [Docker](#docker) и переменную **`HOST_PORT`**). Подробнее — ниже.

## Docker

**Шпаргалка команд (сборка, up, логи, проверки):** [DOCKER.md](DOCKER.md).

Локальный запуск **`python -m recorder`** из venv **не требует Docker и не меняется**.

Нужны **Docker** и **Docker Compose** (v2, команда `docker compose`). В корне репозитория:

```bash
cd /path/to/ffmpeg-stream-rec
cp .env.example .env
# В .env обязательно задайте SECRET_KEY; при занятом порте — HOST_PORT (см. .env.example)

mkdir -p docker-data
# На части хостов (в т.ч. Synology DSM) Docker не создаёт каталог для bind-mount сам —
# без mkdir возможна ошибка: Bind mount failed: '.../docker-data' does not exist

docker compose build
docker compose up -d
```

Интерфейс: **http://127.0.0.1:8080** или, с другой машины в сети, **http://IP-адрес-хоста:8080**. Порт на хосте задаётся **`HOST_PORT`** в `.env` (по умолчанию **8080** в `docker-compose.yml`).

Данные на диске хоста — каталог **`docker-data/`** рядом с `docker-compose.yml` (bind-mount на **`/data`** в контейнере):

- **`docker-data/recordings/`** — MP4;
- **`docker-data/state.sqlite3`** — состояние сессий;
- **`docker-data/logs/`** — логи приложения.

Подкаталоги создаются при первом запуске. Чтобы перенести установку на другой хост, скопируйте репозиторий вместе с **`docker-data/`**.

Дополнительные команды:

```bash
docker compose logs -f recorder   # поток логов контейнера
docker compose ps
docker compose down               # остановка; каталог docker-data/ не удаляется
```

Переменные **`RECORDINGS_ROOT`**, **`STATE_DB_PATH`**, **`LOG_DIR`** для путей внутри контейнера задаёт **`docker-compose.yml`** (`environment`). Одноимённые строки в **`.env`** на эти пути в Docker **не влияют** — они используются при локальном запуске без Docker.

Опционально для доступа с проверкой токена: **`RECORDING_AUTH_TOKEN`** в `.env` (см. комментарии в `.env.example`).

Если вы раньше поднимали сервис с именованным томом **`recorder-data`**, старые файлы остались в том томе; при необходимости скопируйте MP4 в **`docker-data/recordings/`** (путь к данным на хосте смотрите через `docker volume inspect` для нужного тома).

**Диагностика записи:** по умолчанию stderr FFmpeg **не** идёт в API (иначе на macOS/Jupyter при HLS можно забить пайп и получить **0 B**). Чтобы в **`/record/status`** было поле **`ffmpeg_stderr_excerpt`**, задайте в **`.env`**: **`RECORDING_FFMPEG_STDERR_PIPE=1`**. Логи приложения: **`LOG_DIR/app.log`**. В Docker: `ls -la docker-data/recordings` и `docker compose logs recorder --tail 80`.

## Jupyter Notebook

Откройте папку **`ffmpeg-stream-rec` как корень workspace** в Cursor/VS Code.

В репозитории задано:

- [`.vscode/settings.json`](.vscode/settings.json) — интерпретатор по умолчанию `${workspaceFolder}/.venv/bin/python`.
- В ноутбуке [notebooks/dev_server.ipynb](notebooks/dev_server.ipynb) в метаданных указано ядро **`Python (ffmpeg-stream-rec .venv)`**.

После **File → Open Folder…** на этот репозиторий выполните в терминале из корня:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m ipykernel install --user --name=ffmpeg-stream-rec --display-name="Python (ffmpeg-stream-rec .venv)"
```

Перезагрузите окно (**Developer: Reload Window**), откройте ноутбук и при запросе ядра выберите **Python (ffmpeg-stream-rec .venv)**. Затем выполните **кодовую** ячейку — в выводе будет проверка HTTP и ссылка на http://127.0.0.1:5000 .

## Тестовый поток

В ТЗ указан пример ссылки на HLS (раздел B.1 спецификации). Используй только потоки, на которые у тебя есть право записи.

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `FLASK_RUN_HOST` | Адрес при `python -m recorder` (по умолчанию `127.0.0.1`; в Docker обычно `0.0.0.0`) |
| `FLASK_RUN_PORT` | Порт при `python -m recorder` (по умолчанию `5000`; см. занятый порт выше) |
| `HOST_PORT` | Только Docker Compose: порт на хосте для проброса на `5000` внутри контейнера (по умолчанию `8080` в `docker-compose.yml`) |
| `RECORDINGS_ROOT` | Корень сохранения файлов при **локальном** запуске; в Docker задаётся в compose (`/data/recordings` → `docker-data/recordings/`) |
| `STATE_DB_PATH` | SQLite для состояния сессий (локально); в Docker — **`docker-data/state.sqlite3`** |
| `LOG_DIR` | Каталог логов при локальном запуске; в Docker — **`docker-data/logs/`** |
| `MAX_INDEPENDENT_SESSIONS` | Лимит параллельных независимых записей (по умолчанию 2) |
| `MAX_CONTINUATIONS` | Лимит авто‑продолжений после аварии (по умолчанию 5) |
| `DEFAULT_RECORDING_BASENAME` | Подставляется в форму и в поле, если оставить пустым (по умолчанию `steam1`) |
| `RECORDING_SHUTDOWN_HOOKS` | Если не `0`/`false` — при SIGTERM, SIGINT и при завершении процесса активные записи останавливаются как по кнопке «Стоп» (по умолчанию включено) |
| `RECORDING_SHUTDOWN_WAIT_SEC` | Сколько секунд ждать смены статуса сессий перед выходом процесса (по умолчанию 90) |
| `RECORDING_AUTH_TOKEN` | Если задан — доступ к API/UI только с `Authorization: Bearer …` |

При остановке сервера записи завершаются штатно: FFmpeg получает мягкое завершение, файлы MP4 обычно остаются воспроизводимыми. Если процесс убит через **SIGKILL** (`kill -9`), это не перехватывается — возможен обрыв файла. В Jupyter обработчик сигналов может не установиться (не главный поток); тогда перед остановкой ядра лучше нажать «Стоп» в UI.
