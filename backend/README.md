# Beeline Campaign AI Backend

FastAPI service and Python tariff campaign agent for the HackAlem case.
The data is synthetic and the API evaluates runs in the provided mock environment.

## Run the Full Application

From the repository root, in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

The script starts the API and React frontend. The API documentation is usually at
http://127.0.0.1:8000/docs. If a port is occupied, use the URLs printed in the terminal.

## Run the API by Itself

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --app-dir backend --host 127.0.0.1 --port 8000
```

The API exposes `GET /health`, `POST /runs`, `GET /runs/{run_id}`,
`GET /runs/{run_id}/result`, and `GET /runs/{run_id}/submission`.
Runs are queued and processed one at a time.

## Data and Results

The agent uses the case customer profile and historical tariff transitions,
then runs pilots through the environment's public interface. The response reports
the final campaigns, public pilot history, and mock scoring metrics from the same
agent run. CSV downloads use those saved campaigns and do not rerun the agent.

Completed and failed runs are saved as local JSON under `backend/storage/runs/`
and restored after an API restart. Run a single Uvicorn worker. The storage is
local to this machine and is not a shared database.

The agent does not call external LLM services. It needs no model API key.
Mock metrics are a demonstration and do not predict the hidden judging score
or real-world revenue.

## Agent Evaluation and Submission

From the repository root:

```powershell
cd backend
..\.venv\Scripts\python.exe local_eval.py
..\.venv\Scripts\python.exe make_submission.py
```

This creates `backend/submission.csv` from the submitted agent. Submission
artifacts are `agent.py`, `submission.csv`, and the dependencies required
by the case instructions. The website and API are not required for judging
the standalone agent.
