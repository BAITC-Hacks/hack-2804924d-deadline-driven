# HackAlem: Beeline Campaign AI

Hackathon team repository for Deadline Driven.

Здесь зафиксирована проверенная сборка интерфейса, API и агента.
Дальнейшая работа участников в ветках `backend-api` и `agent-strategy`
ведётся отдельно; их более новые изменения в этот снимок не объединены.

## Запуск на Windows

В PowerShell:

```powershell
cd C:\HackAlem
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Скрипт поднимает Python API и React/Vite в фоне. Обычно сайт доступен на
http://localhost:5173, API на http://127.0.0.1:8000/docs.
Если порт занят, выбирается следующий свободный; точные адреса печатаются в терминале.
Повторная команда не запускает ещё одну копию работающих серверов.

Нужны Node.js 22.12+ (или 24+) и Windows Python 3.12+.
На этом ноутбуке уже подготовлена `.venv`. На другом компьютере можно указать Python:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Python C:\Python312\python.exe
```

Зависимости устанавливаются автоматически, если отсутствуют. Для обновления по
`requirements.txt` и `package-lock.json` используйте `start.ps1 -Install`.
Логи находятся в `.run`; эти файлы и окружения не нужно отправлять в GitHub.

Остановка (только серверов, запущенных этим скриптом):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

## Состав проекта

- `frontend`: интерфейс React + TypeScript + Vite.
- `backend`: основной FastAPI и улучшенный `agent.py`, данные и оценка.
- `backend_api`: только локальная архивная копия API с шаблонным агентом;
  не загружается в эту сборку и отдельно не запускается. Ветка `backend-api`
  на GitHub остаётся отдельной рабочей веткой участника.

Схема: React → `/api` (прокси Vite) → FastAPI → `backend/agent.py` → mock-среда.
Vite использует `API_TARGET` (по умолчанию http://127.0.0.1:8000).
Для отдельного развёртывания фронта можно задать `VITE_API_BASE_URL`, а на API
добавить origin фронта в CORS. `dist` сам по себе не содержит Python API или прокси.
Это локальный прототип, не публичный сервер с авторизацией.

## Проверка

На сайте нажмите «Запустить агента». После завершения появится таблица,
а «Экспорт CSV» скачает `submission.csv` именно этого запуска.
Фронт опрашивает статус раз в секунду, останавливается при ошибке и показывает её.
Старые запуски исчезают после перезапуска API; повторите запуск.

Кампании, финансовые показатели `metrics` и история `pilots` приходят из `/result`
одного запуска. `run_report.py` запускает агента ровно один раз и оценивает его
пилоты и итоговый план через `scoring_core.py`, как `local_eval.py`.
Затраты включают пилоты и итоговые кампании; остаток бюджета показан после всех затрат.
Код самого агента не меняется и не получает доступ к данным скоринга.
Mock-среда использует синтетические эффекты: это не прогноз балла судейства.

В этих двух папках разные агенты: при seed=42 версия `backend_api` возвращает
2 SMS-кампании, а основная версия `backend` возвращает 3 рекламные кампании.
Это проверено выполнением обеих версий, а не данные-заглушки в интерфейсе.

```powershell
cd C:\HackAlem
.\.venv\Scripts\python.exe -m unittest discover -s backend -p "test_*.py" -v
cd frontend
npm test
npm run lint
npm run build
cd ..\backend
..\.venv\Scripts\python.exe local_eval.py
```

Агент сдаётся независимо от сайта. CSV можно также сформировать командой
`..\.venv\Scripts\python.exe make_submission.py` из `backend`.
