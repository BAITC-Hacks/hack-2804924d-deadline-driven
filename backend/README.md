# HackAlem — Beeline Campaign Agent

Python-бэкенд для демонстрации агента тарифных маркетинговых кампаний.
Данные синтетические, предоставлены в пакете хакатона.
Текущий agent.py — улучшенная стратегия команды; описание в STRATEGY.md.
Это версия бэкенда данной сборки. Локальная архивная папка backend_api
содержит шаблонного агента и не входит в эту сборку репозитория.

## Запуск на Windows

Общий запуск сайта и API из C:\HackAlem: `powershell -ExecutionPolicy Bypass -File .\start.ps1`.
Для отдельного запуска API после установки зависимостей откройте PowerShell в C:\HackAlem:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api:app --app-dir backend --host 127.0.0.1 --port 8000
```

Документация API: http://127.0.0.1:8000/docs
API находит данные относительно своего файла, независимо от текущей папки терминала.

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
API возвращает кампании, `metrics` и `pilots` из одного запуска агента.
В `metrics`: `net_arpu_gain` (чистый прирост), `total_cost` (общие затраты),
`total_budget` и `remaining_budget` (остаток после пилотов и итоговых кампаний).
Считается тем же `scoring_core.py`, что используется в `local_eval.py`.
В `pilots` передаётся публичная `env.pilot_history`: имя `pilot`, `target_tariff`,
`channel`, `n_customers`, `cost`, `observed_lift_ratio`, `observed_lift_total`,
`remaining_budget`, `remaining_contacts`. Остатки в строке пилота относятся
к моменту этого пилота, а не к завершению итогового плана.
Финансовый отчёт оценивает демонстрационную среду, не реальные доходы и не балл судейства.
CSV по-прежнему содержит только итоговые кампании, без финансовых полей и пилотов.
Сервис предназначен для локальной разработки; авторизация и постоянное хранилище не реализованы.

## Проверка и сдача

```powershell
cd backend
..\.venv\Scripts\python.exe local_eval.py
..\.venv\Scripts\python.exe local_eval.py --runs 10
..\.venv\Scripts\python.exe make_submission.py
```

Для сдачи нужны agent.py, submission.csv и зависимости; API не требуется для запуска агента.
Локальный результат служит проверкой механики, а не гарантией финального балла.
