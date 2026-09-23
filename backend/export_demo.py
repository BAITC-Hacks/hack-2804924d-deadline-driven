"""Generate JSON for a dashboard from public env data and Agent.report only."""
import json
from pathlib import Path

from agent import Agent
from mock_environment import make_mock_env


def main():
    env, _ = make_mock_env(seed=42)
    agent = Agent()
    campaigns = agent.act(env)
    payload = {"environment": "mock", "seed": 42, "campaigns": campaigns,
               "report": agent.report}
    Path("demo_report.json").write_text(json.dumps(payload, ensure_ascii=False,
                                                  indent=2, allow_nan=False), encoding="utf-8")
    print("Saved demo_report.json; forecasts are not actual scored gains.")


if __name__ == "__main__":
    main()
