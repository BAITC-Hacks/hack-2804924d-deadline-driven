"""One command to check raw plans, official scoring and CSV reproducibility.

Run from the package folder: python verify_submission.py --runs 10
Organizer files are invoked unchanged. This is a development tool, not agent.py.
"""
import argparse
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time

from agent import Agent
from local_eval import evaluate_agent
from make_submission import build_submission
from mock_environment import make_mock_env
from validation import validate_plan


def verify(runs):
    records = []
    for seed in range(runs):
        env, _ = make_mock_env(seed=seed)
        agent = Agent()
        started = time.monotonic()
        campaigns = agent.act(env)
        runtime = time.monotonic()-started
        summary = validate_plan(env, campaigns, agent.report)
        if runtime >= 300:
            raise ValueError(f"Agent exceeds the template's stricter 5-minute time limit: {runtime}")
        if len(agent.report["pilots"]) > 20:
            raise ValueError("More than 20 completed pilots")
        if any(not 10 <= p["n"] <= 200 for p in agent.report["pilots"]):
            raise ValueError("A pilot lies outside the stated size range")
        json.dumps(agent.report, allow_nan=False)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = evaluate_agent(Agent(), seed=seed, verbose=True)
        if (result is None or "Статус: PASS" not in buffer.getvalue()
                or "Агент упал" in buffer.getvalue() or "отброшена" in buffer.getvalue()):
            raise RuntimeError(f"Official validation failed at seed {seed}: {buffer.getvalue()}")
        net = float(result["net_arpu_gain"])
        if not math.isfinite(net):
            raise ValueError("Scoring returned non-finite net gain")
        records.append({"seed": seed, **summary, "pilot_count": len(agent.report["pilots"]),
                        "total_cost": agent.report["pilot_cost"]+summary["final_cost"],
                        "total_contacts": agent.report["pilot_contacts"]+summary["final_contacts"],
                        "net": net, "runtime_seconds": runtime})
    # Invoke the actual supplied exporter twice, then independently compare the
    # expected frame. Do not hand-edit submission.csv.
    snapshots = []
    for _ in range(2):
        subprocess.run([sys.executable, "-X", "utf8", "make_submission.py"],
                       check=True, capture_output=True)
        snapshots.append(Path("submission.csv").read_bytes())
    if snapshots[0] != snapshots[1]:
        raise ValueError("CSV changes between identical runs")
    # read_text normalizes Windows CRLF; use the same newline convention for
    # this independent comparison (the two actual exports remain byte-checked).
    expected = build_submission(Agent()).to_csv(index=False, lineterminator="\n")
    if Path("submission.csv").read_text(encoding="utf-8") != expected:
        raise ValueError("CSV does not match agent output")
    nets = [r["net"] for r in records]
    return {"status": "PASS", "environment": "official participant mock",
            "csv_reproducible": True, "runs": records,
            "summary": {"runs": runs, "positive": sum(n > 0 for n in nets),
                        "mean_net": statistics.mean(nets), "min_net": min(nets),
                        "max_net": max(nets), "max_runtime_seconds": max(r["runtime_seconds"] for r in records)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    report = verify(args.runs)
    Path("verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], **report["summary"],
                      "csv_reproducible": report["csv_reproducible"]}, indent=2))
