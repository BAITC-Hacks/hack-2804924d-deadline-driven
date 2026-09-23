"""Paired benchmark using the official evaluator, never hidden effect data.

python benchmark.py --runs 10 --start-seed 0
python benchmark.py --runs 10 --start-seed 100 --output benchmark_holdout.json
"""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import statistics
import time

from agent import Agent as ProductionAgent
from agent_confirmed import Agent as ConfirmedAgent
from agent_template import Agent as TemplateAgent
from local_eval import evaluate_agent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--start-seed", type=int, default=0)
    parser.add_argument("--output", default="benchmark_results.json")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    versions = {"template": TemplateAgent, "production": ProductionAgent,
                "confirmed_channels": ConfirmedAgent}
    rows = []
    for seed in range(args.start_seed, args.start_seed + args.runs):
        for name, cls in versions.items():
            start = time.monotonic()
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                result = evaluate_agent(cls(), seed=seed, verbose=False)
            if result is None or "Агент упал" in buffer.getvalue():
                raise RuntimeError(f"Evaluation failed: {name}, seed={seed}: {buffer.getvalue()}")
            row = {"seed": seed, "agent": name,
                   "net": float(result["net_arpu_gain"]),
                   "pilots": int(result["n_pilots"]),
                   "runtime_seconds": round(time.monotonic()-start, 3),
                   "evaluator_messages": buffer.getvalue()}
            rows.append(row)
            print(f'{name:20} seed={seed:3} net={row["net"]:12,.0f}', flush=True)
    summary = {}
    for name in versions:
        sample = [r["net"] for r in rows if r["agent"] == name]
        summary[name] = {"runs": len(sample), "positive": sum(v > 0 for v in sample),
                         "mean": statistics.mean(sample), "median": statistics.median(sample),
                         "min": min(sample), "max": max(sample)}
    payload = {"environment": "official participant mock", "start_seed": args.start_seed,
               "summary": summary, "runs": rows}
    Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
