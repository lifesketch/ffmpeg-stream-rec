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

Локальный запуск **`python -m recorder`** из venv **не требует Docker и не меняется**.

Образ и `docker-compose.yml` — отдельный способ развёртывания (в т.ч. Synology). В compose для контейнера заданы пути **`/data/recordings`**, **`/data/state.sqlite3`**, **`/data/logs`** и один том, чтобы записи и SQLite переживали пересоздание контейнера.

```bash
cp .env.example .env   # SECRET_KEY обязателен; см. комментарии про HOST_PORT
docker compose build
docker compose up -d
```

- Интерфейс по умолчанию: **http://127.0.0.1:8080** (`HOST_PORT` из `.env` или значение по умолчанию в `docker-compose.yml`).
- Если порт на машине занят — выставьте в `.env`, например: **`HOST_PORT=9000`**.
- На NAS имеет смысл заменить именованный том на **bind-mount** к каталогам на диске (записи + каталог с SQLite).

Остановка без удаления данных: `docker compose down`. Для доступа из сети задайте **`RECORDING_AUTH_TOKEN`** в `.env`.

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
| `RECORDINGS_ROOT` | Корень сохранения файлов (режим 1 и базовый путь для 2b) |
| `STATE_DB_PATH` | SQLite для состояния сессий |
| `MAX_INDEPENDENT_SESSIONS` | Лимит параллельных независимых записей (по умолчанию 2) |
| `MAX_CONTINUATIONS` | Лимит авто‑продолжений после аварии (по умолчанию 5) |
| `DEFAULT_RECORDING_BASENAME` | Подставляется в форму и в поле, если оставить пустым (по умолчанию `steam1`) |
| `RECORDING_SHUTDOWN_HOOKS` | Если не `0`/`false` — при SIGTERM, SIGINT и при завершении процесса активные записи останавливаются как по кнопке «Стоп» (по умолчанию включено) |
| `RECORDING_SHUTDOWN_WAIT_SEC` | Сколько секунд ждать смены статуса сессий перед выходом процесса (по умолчанию 90) |
| `RECORDING_AUTH_TOKEN` | Если задан — доступ к API/UI только с `Authorization: Bearer …` |

При остановке сервера записи завершаются штатно: FFmpeg получает мягкое завершение, файлы MP4 обычно остаются воспроизводимыми. Если процесс убит через **SIGKILL** (`kill -9`), это не перехватывается — возможен обрыв файла. В Jupyter обработчик сигналов может не установиться (не главный поток); тогда перед остановкой ядра лучше нажать «Стоп» в UI.
