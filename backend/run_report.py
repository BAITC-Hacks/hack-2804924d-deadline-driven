"""Local demonstration reporting. Never imported by the submitted agent."""
import json
from pathlib import Path

import pandas as pd

from agent import Agent
from make_submission import CAMPAIGN_COLUMNS
from mock_environment import make_mock_env, _mock_impact_model, _mock_fallback
from scoring_core import MAX_CAMPAIGNS, sanitize_campaigns, score_campaigns

BASE_DIR = Path(__file__).resolve().parent


def build_run_report(agent=None, seed=42):
    env, internals = make_mock_env(
        seed=seed, data_dir=str(BASE_DIR / "data"),
        profile_path=str(BASE_DIR / "customer_profile.csv"),
    )
    # Exactly one call: pilots, campaigns and score all belong to this run.
    campaigns = (agent if agent is not None else Agent()).act(env) or []
    campaigns = sanitize_campaigns(campaigns, env.tariffs)[:MAX_CAMPAIGNS]
    final_df = pd.DataFrame(campaigns).reindex(columns=CAMPAIGN_COLUMNS)
    pilots = internals.executed_pilot_campaigns()
    all_campaigns = pd.DataFrame(pilots + campaigns)
    for col in CAMPAIGN_COLUMNS + ["explicit_ids"]:
        if col not in all_campaigns.columns:
            all_campaigns[col] = None
    model = _mock_impact_model(pd.read_csv(BASE_DIR / "data/change_tariff.csv"))
    score = score_campaigns(
        all_campaigns, env.customer_profile, model, env.tariffs,
        env.customer_profile["predicted_arpu"].sum(), _mock_fallback,
        team_id="local",
    )
    # Use pandas JSON normalization for numpy scalars, NaN and infinite ROI.
    metrics = {k: v for k, v in score.items() if k != "campaigns_detail"}
    metrics.update({
        "total_budget": float(env.total_budget),
        "n_pilots": len(pilots),
        "remaining_budget": env.total_budget - score["total_cost"],
        "remaining_contacts": env.max_total_contacts - score["total_contacts"],
    })
    report = {
        "environment": "mock",
        "campaign_count": len(final_df),
        "campaigns": json.loads(final_df.to_json(orient="records")),
        "pilots": env.pilot_history,
        "metrics": metrics,
        "campaign_details": score["campaigns_detail"],
        "after_pilots": {
            "remaining_budget": env.remaining_budget,
            "remaining_contacts": env.remaining_contacts,
            "pilots_left": env.pilots_left,
        },
    }
    return json.loads(pd.Series(report, dtype=object).to_json(force_ascii=False, double_precision=15))
