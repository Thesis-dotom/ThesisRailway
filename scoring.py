"""Model 3.0: dated financials, independent scores and explicit peer evidence.

Weights and screening thresholds are provisional research rules, not validated
return forecasts. Analyst targets and momentum are context only.
"""
from datetime import datetime, timezone
import math
import statistics

MODEL_VERSION = '3.0'
MIN_PEERS = 8
QUALITY = [
    ('Operating return on capital', 'operating_return_pct', 20, [0, 25]),
    ('Three-year operating margin', 'operating_margin_3y_pct', 15, []),
    ('Three-year free-cash-flow margin', 'fcf_margin_3y_pct', 15, []),
    ('Cash-flow consistency', 'fcf_positive_years_pct', 10, [0, 100]),
    ('Net debt / EBITDA', 'net_debt_to_ebitda', 15, [0, 4]),
    ('Annualized revenue growth', 'revenue_cagr_pct', 10, [-5, 20]),
    ('Annualized diluted EPS growth', 'eps_cagr_pct', 15, [0, 25]),
]
OPPORTUNITY = [
    ('Annual earnings yield', 'earnings_yield_pct', 35, []),
    ('Annual free-cash-flow yield', 'fcf_yield_pct', 35, []),
    ('Annual EBITDA / enterprise value', 'ebitda_yield_pct', 30, []),
]
PEER_KEYS = {'operating_margin_3y_pct', 'fcf_margin_3y_pct',
             'earnings_yield_pct', 'fcf_yield_pct', 'ebitda_yield_pct'}
UNSUPPORTED = {'Financial Services', 'Real Estate'}


def utcnow():
    return datetime.now(timezone.utc)


def age_days(value, now=None):
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return ((now or utcnow()) - date).total_seconds() / 86400
    except (ValueError, TypeError, AttributeError):
        return math.inf


def valid(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def linear(value, low, high):
    return max(0.0, min(1.0, (value - low) / (high - low)))


def peer_reference(report, reports, now=None):
    now = now or utcnow()
    peers = [r for r in reports.values() if r.get('symbol') != report['symbol']
             and r.get('sector') not in UNSUPPORTED
             and -1 <= age_days(r.get('annual_period_end'), now) <= 550]
    result = {}
    for key in PEER_KEYS:
        for category in ('industry', 'sector'):
            label = report.get(category)
            if not label or label.startswith('Unknown'):
                continue
            selected = [r for r in peers if r.get(category) == label and valid(r.get(key))
                        and (key not in {x[1] for x in OPPORTUNITY}
                             or -1 <= age_days(r.get('market_data_as_of'), now) <= 7)]
            if len(selected) < MIN_PEERS:
                continue
            median = statistics.median(r[key] for r in selected)
            if median <= 0:
                continue
            result[key] = {'median': median, 'count': len(selected), 'basis': category,
                           'group': label, 'as_of': now.isoformat(),
                           'symbols': sorted(r['symbol'] for r in selected),
                           'oldest_period': min(r['annual_period_end'] for r in selected),
                           'newest_period': max(r['annual_period_end'] for r in selected)}
            break
    return result


def score_component(name, value, maximum, bounds, reference=None):
    if not valid(value):
        return None
    if name == 'Net debt / EBITDA':
        fraction = 1 - linear(value, *bounds)
    elif bounds:
        fraction = linear(value, *bounds)
    elif reference and reference.get('count', 0) >= MIN_PEERS and valid(reference.get('median')) and reference['median'] > 0:
        fraction = linear(value / reference['median'], 0, 2)
    else:
        return None
    return round(maximum * fraction, 4)


def evaluate(report, now=None, peers=None):
    now = now or utcnow()
    references = peer_reference(report, peers, now) if peers is not None else report.get('peer_reference', {})
    # A saved reference is usable only with its original date, never silently freshened.
    references = {key: ref for key, ref in references.items() if -1 <= age_days(ref.get('as_of'), now) <= 8}
    report['peer_reference'] = references
    supported = report.get('sector') not in UNSUPPORTED
    statement_recent = -1 <= age_days(report.get('annual_period_end'), now) <= 550
    market_recent = -1 <= age_days(report.get('market_data_as_of'), now) <= 7
    quote_ok = market_recent and valid(report.get('price')) and report['price'] > 0 and valid(report.get('market_cap')) and report['market_cap'] > 0
    groups, evidence, missing_groups, raw_missing = [], [], [], []
    for rubric, group_name in [(QUALITY, 'quality'), (OPPORTUNITY, 'opportunity')]:
        rows, missing = [], []
        for name, key, weight, bounds in rubric:
            value = report.get(key)
            note = None
            known_nonpositive = (key == 'eps_cagr_pct' and report.get('eps_growth_state') == 'nonpositive_history') or (key == 'net_debt_to_ebitda' and report.get('leverage_state') == 'nonpositive_ebitda')
            if known_nonpositive:
                score = 0.0
                note = 'Nonpositive earnings in the measured period; zero points under the stated rule.'
            else:
                score = score_component(name, value, weight, bounds, references.get(key))
            if score is None:
                if not valid(value):
                    missing.append(name)
                    raw_missing.append(name)
                else:
                    missing.append(name + ': at least 8 comparable peer observations required')
            rows.append((name, score, weight))
            evidence.append({'factor': name, 'key': key, 'group': group_name, 'input': value,
                             'score': score, 'maximum': weight, 'note': note,
                             'peer': references.get(key)})
        if not statement_recent:
            missing.append('Recent aligned annual statements')
        if group_name == 'quality' and report.get('quality_window_years') is None:
            missing.append('Three consecutive annual statements')
        if group_name == 'opportunity':
            if not quote_ok:
                missing.append('Recent positive price and market capitalization')
            if not report.get('currency_compatible'):
                missing.append('Matching quote and financial currencies')
        groups.append(rows)
        missing_groups.append(list(dict.fromkeys(missing)))
    q_missing, o_missing = missing_groups
    q_ok = supported and not q_missing
    o_ok = supported and not o_missing
    q = round(sum(row[1] for row in groups[0]), 1) if q_ok else None
    o = round(sum(row[1] for row in groups[1]), 1) if o_ok else None
    combined = round(q + o, 1) if q_ok and o_ok else None
    screen_match = combined is not None and q >= 60 and combined >= 150
    if not supported:
        category, answer, reason = 'excluded', 'Not supported', 'Financial and real-estate businesses need separate models.'
    elif screen_match:
        category, answer, reason = 'screen', 'Meets research screen', 'Meets the provisional Quality ≥60 and combined ≥150 rules. This is a research priority, not a buy recommendation.'
    elif q_ok and q >= 70:
        category, answer, reason = 'watchlist', 'Quality watchlist', 'Quality is at least 70. Review valuation, business risks and company filings before considering an investment.'
    elif q_ok or o_ok:
        category, answer, reason = 'research', 'Available for research', 'The company remains visible for research. A lower score or an incomplete second score is not a sell instruction.'
    else:
        category, answer, reason = 'excluded', 'Insufficient data', 'Scores are withheld until the required dated inputs and comparable peer data are available.'
    report.update(model_version=MODEL_VERSION, business_quality=q, opportunity=o,
                  business_breakdown=groups[0], opportunity_breakdown=groups[1],
                  business_label='Financial quality' if q_ok else 'Not rated',
                  opportunity_label='Relative valuation' if o_ok else 'Not rated',
                  score_evidence=evidence, quality_missing=q_missing, opportunity_missing=o_missing,
                  missing_data=list(dict.fromkeys(q_missing + o_missing)),
                  quality_complete=q_ok, opportunity_complete=o_ok, eligible_data=q_ok and o_ok,
                  fetch_complete=supported and not raw_missing and statement_recent and quote_ok
                      and report.get('quality_window_years') is not None and bool(report.get('currency_compatible')),
                  screen_match=screen_match, category=category,
                  rating_source='Quantitative research · model ' + MODEL_VERSION + ' · provisional weights',
                  decision={'combined': combined, 'answer': answer, 'class': 'yes' if screen_match else 'maybe', 'reason': reason})
    positives, risks = [], []
    for name, key in [('Annualized revenue growth', 'revenue_cagr_pct'),
                      ('Annualized diluted EPS growth', 'eps_cagr_pct'),
                      ('Median annual operating margin', 'operating_margin_3y_pct'),
                      ('Median annual free-cash-flow margin', 'fcf_margin_3y_pct')]:
        value = report.get(key)
        if valid(value):
            (positives if value > 0 else risks).append(f'{name}: {value:.1f}%. See the dated annual periods below.')
    if valid(report.get('net_debt_to_ebitda')):
        risks.append(f"Net debt / annual EBITDA: {report['net_debt_to_ebitda']:.2f}×. Review debt maturities and liquidity separately.")
    if report.get('annual_periods') and (report['annual_periods'][0].get('net_income') or 0) < 0:
        risks.append('The latest annual period reported a net loss. Earnings yield receives zero valuation points; unavailable P/E is not treated as a download failure.')
    risks += report.get('metric_notes', [])
    risks.append('Weights and thresholds are not backtested. Peer groups are a limited U.S.-listed sample and can span different fiscal year ends. Moats, management and catalysts require human research.')
    report['why_like'] = positives or ['No complete quantitative strengths are available.']
    report['risks'] = risks
    report['thesis'] = f"{report['name']}: {answer}. {reason}"
    report['full_report'] = {'overview': report.get('business_summary') or f"{report['name']} — {report.get('sector', 'Unknown sector')}. A verified business description is unavailable.",
                             'bull_case': report['why_like'], 'bear_case': risks,
                             'watching': ['Next filings and changes in annual profits, cash flow and financing.',
                                          'Valuation relative to peers; investigate differences in growth, accounting and risk.',
                                          'Analyst targets and price momentum are unscored context, not independently verified fair values.']}
    return report
