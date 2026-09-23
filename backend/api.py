import csv
import io
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from agent import Agent
from make_submission import CAMPAIGN_COLUMNS, build_submission


app = FastAPI(title="Beeline Campaign Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition"],
)

# Фоновые задания выполняются по одному.
executor = ThreadPoolExecutor(max_workers=1)

# Результаты хранятся в памяти до перезапуска сервера.
runs = {}
runs_lock = Lock()

# Защищает агента от одновременного запуска через /preview и /runs.
agent_lock = Lock()


def calculate_result():
    with agent_lock:
        df = build_submission(Agent(), seed=42)

    # Пропуски должны стать null в JSON.
    df = df.astype(object).where(df.notna(), None)

    return {
        "environment": "mock",
        "campaign_count": len(df),
        "campaigns": df.to_dict(orient="records"),
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/preview")
def preview():
    return calculate_result()


def execute_agent(run_id: str):
    with runs_lock:
        runs[run_id]["status"] = "running"

    try:
        result = calculate_result()

        with runs_lock:
            runs[run_id]["result"] = result
            runs[run_id]["status"] = "completed"

    except Exception as exc:
        with runs_lock:
            runs[run_id]["error"] = str(exc)
            runs[run_id]["status"] = "failed"


@app.post("/runs", status_code=202)
def create_run():
    run_id = str(uuid4())

    with runs_lock:
        runs[run_id] = {
            "status": "queued",
            "result": None,
            "error": None,
        }

    executor.submit(execute_agent, run_id)

    return {"run_id": run_id}


@app.get("/runs/{run_id}")
def get_run_status(run_id: str):
    with runs_lock:
        run = runs.get(run_id)

        if run is None:
            raise HTTPException(
                status_code=404,
                detail="Запуск не найден",
            )

        return {
            "run_id": run_id,
            "status": run["status"],
            "error": run["error"],
        }


@app.get("/runs/{run_id}/result")
def get_run_result(run_id: str):
    with runs_lock:
        run = runs.get(run_id)

        if run is None:
            raise HTTPException(
                status_code=404,
                detail="Запуск не найден",
            )

        if run["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Результат ещё недоступен. "
                    f"Статус: {run['status']}"
                ),
            )

        return run["result"]


@app.get("/runs/{run_id}/submission", response_class=Response)
def download_submission(run_id: str):
    # Берём сохранённый результат, не запускаем агента повторно.
    result = get_run_result(run_id)

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=CAMPAIGN_COLUMNS,
    )
    writer.writeheader()
    writer.writerows(result["campaigns"])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="submission.csv"'
            )
        },
    )