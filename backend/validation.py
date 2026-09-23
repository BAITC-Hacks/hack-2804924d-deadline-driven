"""Validate an agent plan using ONLY public environment data.

Unlike the official sanitizer, this fails on invalid output instead of silently
dropping a campaign. It does not calculate true or hidden campaign effects.
"""
from math import isfinite


FILTER_COLUMNS = {
    "filter_current_tariff": "current_tariff",
    "filter_arpu_segment": "arpu_segment",
    "filter_data_segment": "data_segment",
    "filter_call_segment": "call_segment",
}


def validate_plan(env, campaigns, report=None, require_pilot=True):
    if not isinstance(campaigns, list) or not 1 <= len(campaigns) <= 10:
        raise ValueError("The final plan must contain 1..10 campaigns")
    allowed = set(FILTER_COLUMNS) | {"target_tariff", "channel", "campaign_name"}
    valid_tariffs = set(env.tariffs["tariff_plan_code"])
    total_cost, contacts, seen = 0., 0, set()
    details = []
    for campaign in campaigns:
        if not isinstance(campaign, dict) or set(campaign)-allowed:
            raise ValueError("Unexpected campaign type or keys")
        if campaign.get("target_tariff") not in valid_tariffs:
            raise ValueError("Unknown target tariff")
        if campaign.get("channel") not in env.channels:
            raise ValueError("Unknown channel")
        audience = env.customer_profile
        for key, column in FILTER_COLUMNS.items():
            value = campaign.get(key)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Filters must be nonempty strings or omitted")
            if key == "filter_current_tariff":
                wanted = [v.strip() for v in value.split(";") if v.strip()]
                audience = audience[audience[column].isin(wanted)]
            else:
                audience = audience[audience[column] == value]
        ids = set(audience["ID_NUMBER"])
        if len(ids) != len(audience) or not 1 <= len(ids) <= 5000:
            raise ValueError("Invalid audience size or duplicate customer IDs")
        if ids & seen:
            raise ValueError("Final campaigns overlap; this agent promises disjoint audiences")
        seen.update(ids)
        rate = float(env.channels[campaign["channel"]]["cost_per_contact"])
        if not isfinite(rate) or rate < 0:
            raise ValueError("Invalid channel cost")
        cost = len(ids)*rate
        total_cost += cost
        contacts += len(ids)
        details.append({"contacts": len(ids), "cost": cost})
    if total_cost > float(env.remaining_budget)+1e-7 or contacts > int(env.remaining_contacts):
        raise ValueError("Final plan exceeds remaining resources after pilots")
    if report is not None:
        if abs(float(report["final_cost"])-total_cost) > 1e-7 or report["final_contacts"] != contacts:
            raise ValueError("Reported totals disagree with actual filter audiences")
        if require_pilot and not report["pilots"]:
            raise ValueError("No successful pilot: the submission does not meet the case requirements")
        if len(report["campaigns"]) != len(details):
            raise ValueError("Report campaign count differs from the returned plan")
        for actual, logged in zip(details, report["campaigns"]):
            if actual["contacts"] != logged["contacts"] or abs(actual["cost"]-logged["cost"]) > 1e-7:
                raise ValueError("A campaign report disagrees with its filter audience")
    return {"campaign_count": len(campaigns), "final_contacts": contacts,
            "final_cost": total_cost, "disjoint_audiences": True}
