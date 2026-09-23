"""A single-run adapter for a backend; no FastAPI dependency required."""
import json

from agent import Agent
from validation import validate_plan


def run_agent(env):
    agent = Agent()
    campaigns = agent.act(env)
    checks = validate_plan(env, campaigns, agent.report)
    result = {"campaign_count": len(campaigns), "campaigns": campaigns,
              "report": agent.report, "validation": checks}
    # Fail at the API boundary rather than emit invalid NaN/Infinity JSON.
    json.dumps(result, allow_nan=False)
    return result
