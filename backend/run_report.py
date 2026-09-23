"""Demo reporting outside the agent, using the same scorer as local_eval.py."""

from pathlib import Path

import pandas as pd

from make_submission import CAMPAIGN_COLUMNS, SUBMISSION_SEED
from mock_environment import _mock_fallback, _mock_impact_model, make_mock_env
from scoring_core import score_campaigns, validate_strategy


def build_run_report(agent, *, data_dir, profile_path, seed=SUBMISSION_SEED):
    env, internals = make_mock_env(
        seed=seed, data_dir=str(data_dir), profile_path=str(profile_path)
    )
    # Run once: the returned plan, pilot history and score all belong to this env.
    final_campaigns = agent.act(env) or []
    frame = pd.DataFrame(final_campaigns)
    for column in CAMPAIGN_COLUMNS:
        if column not in frame:
            frame[column] = None
    frame = frame[CAMPAIGN_COLUMNS]
    validate_strategy(frame, env.tariffs)
    frame = frame.astype(object).where(frame.notna(), None)

    # Only the reporting layer receives the scorer inputs, never the agent.
    all_campaigns = pd.DataFrame(internals.executed_pilot_campaigns() + final_campaigns)
    for column in [*CAMPAIGN_COLUMNS, "explicit_ids"]:
        if column not in all_campaigns:
            all_campaigns[column] = None
    profile = env.customer_profile
    model = _mock_impact_model(pd.read_csv(Path(data_dir) / "change_tariff.csv"))
    score = score_campaigns(
        all_campaigns, profile, model, env.tariffs,
        profile["predicted_arpu"].sum(), _mock_fallback, team_id="local",
    )
    total_cost = float(score["total_cost"])
    return {
        "environment": "mock",
        "campaign_count": len(frame),
        "campaigns": frame.to_dict(orient="records"),
        "metrics": {
            "net_arpu_gain": float(score["net_arpu_gain"]),
            "total_cost": total_cost,
            "total_budget": float(env.total_budget),
            "remaining_budget": float(env.total_budget) - total_cost,
        },
        "pilots": [dict(pilot) for pilot in env.pilot_history],
    }
