# HackAlem — Beeline Campaign Agent

Python-бэкенд для демонстрации агента тарифных маркетинговых кампаний.
Данные синтетические, предоставлены в пакете хакатона.
Текущий agent.py — базовый шаблон, стратегия пока не улучшена.

## Запуск на Windows

Откройте PowerShell в корне клонированного проекта:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

Документация API: http://127.0.0.1:8000/docs
Все команды выполняются из корня проекта: данные читаются по относительным путям.

## Подключение фронтенда

Каждый разработчик запускает бэкенд у себя. Адрес API: http://127.0.0.1:8000
CORS разрешает http://localhost:5173 и http://127.0.0.1:5173.

1. POST /runs возвращает run_id (HTTP 202).
2. GET /runs/{run_id} — опрос раз в секунду до completed или failed.
3. GET /runs/{run_id}/result — кампании завершённого запуска.
4. GET /runs/{run_id}/submission — CSV того же запуска.

GET /health проверяет доступность. POST /preview выполняет отдельный синхронный расчёт.
Статусы: queued, running, completed, failed. При failed доступно поле error.
Неизвестный run_id даёт 404, ещё не готовый результат — 409.

## Ограничения прототипа

Запуски хранятся в памяти и исчезают при перезапуске, включая --reload.
Используйте один процесс Uvicorn, без нескольких workers.
API работает с мок-средой; результат не предсказывает балл судейства.
API возвращает кампании, но пока не возвращает историю пилотов и финансовый отчёт.
Сервис предназначен для локальной разработки; авторизация и постоянное хранилище не реализованы.

## Проверка и сдача

```powershell
.\.venv\Scripts\python.exe local_eval.py
.\.venv\Scripts\python.exe local_eval.py --runs 10
.\.venv\Scripts\python.exe make_submission.py
```

Для сдачи нужны agent.py, submission.csv и зависимости; API не требуется для запуска агента.
Отрицательный результат базового шаблона означает убыточную стратегию, а не сбой API.
