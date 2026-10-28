"""Transparent screening heuristics; not a validated prediction model."""
from datetime import datetime, timezone
import math

MODEL_VERSION = "2.0"
QUALITY = [
    ("Revenue growth", "revenue_growth_pct", 20, [-10, 0, 5, 15, 30]),
    ("Earnings growth", "earnings_growth_pct", 20, [-10, 0, 5, 15, 30]),
    ("Net profit margin", "profit_margin_pct", 20, [0, 5, 10, 20, 30]),
    ("Return on equity", "roe_pct", 20, [0, 5, 10, 20, 30]),
    ("Debt / equity", "debt_to_equity", 10, [25, 50, 100, 150, 200]),
    ("Free cash flow", "free_cash_flow", 10, []),
]
OPPORTUNITY = [
    ("Trailing P/E", "trailing_pe", 35, [10, 15, 20, 30, 45]),
    ("Analyst target upside", "target_upside_pct", 25, [0, 10, 20, 35, 60]),
    ("Earnings growth", "earnings_growth_pct", 20, [-10, 0, 5, 15, 30]),
    ("Six-month price return", "momentum_pct", 20, [-20, -5, 0, 10, 25]),
]

def utcnow():
    return datetime.now(timezone.utc)

def age_days(value, now=None):
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return ((now or utcnow()) - d).total_seconds() / 86400
    except (ValueError, TypeError, AttributeError):
        return math.inf

def valid(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def score_component(name, value, maximum, bounds):
    if not valid(value):
        return None
    if name == "Free cash flow":
        return maximum if value > 0 else 0
    if name == "Trailing P/E" and value <= 0:
        return 0
    if name == "Debt / equity" and value < 0:
        return 0
    if name in ("Debt / equity", "Trailing P/E"):
        fraction = sum(value <= limit for limit in bounds) / len(bounds)
    else:
        fraction = sum(value >= limit for limit in bounds) / len(bounds)
    return round(maximum * fraction)

def evaluate(report, now=None):
    now = now or utcnow()
    missing = []
    breakdowns = []
    evidence = []
    for rubric in (QUALITY, OPPORTUNITY):
        rows = []
        for name, key, weight, bounds in rubric:
            value = report.get(key)
            score = score_component(name, value, weight, bounds)
            rows.append((name, score, weight))
            if score is None:
                missing.append(name)
            evidence.append({"factor": name, "input": value, "score": score, "maximum": weight})
        breakdowns.append(rows)
    for key in ("price", "market_cap"):
        if not valid(report.get(key)) or report[key] <= 0:
            missing.append(key.replace("_", " ").title())
    if not -1 <= age_days(report.get("market_data_as_of"), now) <= 7:
        missing.append("Recent dated market data")
    if not -1 <= age_days(report.get("financial_period_end"), now) <= 550:
        missing.append("Recent dated financial statements")
    if not -1 <= age_days(report.get("cashflow_period_end"), now) <= 550:
        missing.append("Recent dated cash-flow statement")
    # Ratio comparisons are not meaningful for these businesses without a separate rubric.
    unsupported = report.get("sector") in ("Financial Services", "Real Estate")
    missing = list(dict.fromkeys(missing))
    complete = not missing and not unsupported
    q, o = [sum(row[1] or 0 for row in rows) for rows in breakdowns]
    report.update(business_breakdown=breakdowns[0], opportunity_breakdown=breakdowns[1],
                  score_evidence=evidence, missing_data=missing, eligible_data=complete,
                  model_version=MODEL_VERSION, rating_source="Quantitative screen · model " + MODEL_VERSION)
    if complete:
        report.update(business_quality=q, opportunity=o, business_label="Quantitative quality",
                      opportunity_label="Quantitative opportunity")
        qualifies = q >= 60 and q + o >= 150
        report["decision"] = {"combined": q + o, "answer": "Meets screen" if qualifies else "Below threshold",
                              "class": "yes" if qualifies else "maybe",
                              "reason": "Quality ≥60 and combined ≥150 are required. This screen is a research starting point, not a buy instruction."}
    else:
        report.update(business_quality=None, opportunity=None,
                      business_label="Not rated", opportunity_label="Not rated")
        report["decision"] = {"combined": None, "answer": "Not supported" if unsupported else "Insufficient data",
                              "class": "maybe", "reason": "This model does not cover financial or real-estate businesses." if unsupported
                              else "Rating withheld: " + ", ".join(missing) + "."}
    positives, risks = [], []
    for label, key in [("Revenue growth", "revenue_growth_pct"), ("Earnings growth", "earnings_growth_pct"),
                       ("Net margin", "profit_margin_pct"), ("ROE", "roe_pct")]:
        value = report.get(key)
        if valid(value):
            (positives if value > 0 else risks).append(f"{label}: {value:.1f}% (provider-reported or calculated; see input periods).")
    if valid(report.get("trailing_pe")):
        risks.append(f"Trailing P/E is {report['trailing_pe']:.1f}; compare it with sector peers and earnings durability.")
    if valid(report.get("free_cash_flow")):
        value = report["free_cash_flow"]
        (positives if value > 0 else risks).append(f"Annual free cash flow: {value:,.0f} {report.get('currency', 'reported currency')}.")
    risks.append("The model does not verify management quality, competitive advantages, company catalysts, or analyst target recency.")
    report["why_like"] = positives or ["No verified quantitative positives are available."]
    report["risks"] = risks
    report["thesis"] = (f"{report['name']}: {report['decision']['answer']}. " + report["decision"]["reason"])
    report["full_report"] = {
        "overview": report.get("business_summary") or f"{report['name']} — {report['sector']} / {report['industry']}. A verified business description is unavailable.",
        "bull_case": report["why_like"], "bear_case": risks,
        "watching": ["Next earnings release and changes in revenue, earnings, margins, debt and cash flow.",
                     "Price changes relative to earnings and analyst estimates; analyst targets are not fair-value guarantees.",
                     "Company filings and specific catalysts require separate review."],
    }
    return report
