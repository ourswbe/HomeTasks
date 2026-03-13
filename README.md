# HomeTasks — система учёта домашних заданий

Веб-приложение для курсовой работы по теме домашних заданий.

## Возможности

- Регистрация и вход с выбором роли: **учитель** или **ученик**.
- Учитель добавляет задания с предметом, дедлайном, типом и максимальным баллом.
- Ученик отправляет решение (текст / ссылка / фото / multiple choice).
- Учитель проверяет решения, выставляет оценку и комментарий.
- Фильтр по предметам, статусы выполнения и дедлайны.

## Технологии

- Python 3.11
- Flask + Flask-SQLAlchemy
- SQLite (по умолчанию) **или PostgreSQL**
- Docker / Docker Compose

## База данных

По умолчанию используется SQLite (`sqlite:///hometasks.db`).

Чтобы использовать PostgreSQL, задайте переменную `DATABASE_URL`:

```bash
export DATABASE_URL="postgresql+psycopg2://hometasks:hometasks@localhost:5432/hometasks"
```

Приложение читает:
- `DATABASE_URL`
- `SECRET_KEY`

## Запуск локально (SQLite)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Запуск с PostgreSQL через Docker

```bash
docker compose up --build
```

Будет поднято 2 сервиса:
- `db` (PostgreSQL 16)
- `web` (Flask), доступен на http://localhost:5000

## Важно про старые SQLite базы

Если ранее база была создана старой версией приложения, при старте выполняется
авто-добавление недостающих столбцов (чтобы избежать ошибок вида
`sqlite3.OperationalError: no such column: task.task_type`).

## Основные экраны

- `/register` — регистрация.
- `/login` — авторизация.
- `/tasks` — список заданий, отправка решений, проверка.
- `/tasks/add` — добавление задания (только для учителя).
