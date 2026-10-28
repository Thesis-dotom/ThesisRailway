"""Dated annual inputs. No provider quarterly/TTM ratios enter model 3.0."""
import math
import statistics
import pandas as pd


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def annual_rows(frame):
    if frame is None or frame.empty:
        return {}
    result = {}
    for column in frame.columns:
        try:
            date = pd.Timestamp(column).date().isoformat()
        except (ValueError, TypeError):
            continue
        result[date] = {str(k): number(v) for k, v in frame[column].items()}
    return result


def pick(row, *keys):
    return next((row[k] for k in keys if row.get(k) is not None), None)


def divide(a, b, scale=1):
    return a / b * scale if a is not None and b is not None and b > 0 else None


def complete_median(values, count=3):
    return statistics.median(values) if len(values) == count and all(v is not None for v in values) else None


def extract_annual(income, cashflow, balance, market_cap, quote_currency, financial_currency):
    incomes, cashflows, balances = map(annual_rows, (income, cashflow, balance))
    dates = sorted(set(incomes) & set(cashflows) & set(balances), reverse=True)
    rows = []
    for date in dates:
        inc, cf, bs = incomes[date], cashflows[date], balances[date]
        debt = pick(bs, "Total Debt")
        if debt is None:
            short, long = pick(bs, "Current Debt", "Current Debt And Capital Lease Obligation"), pick(bs, "Long Term Debt", "Long Term Debt And Capital Lease Obligation")
            if short is not None and long is not None:
                debt = short + long
        cash = pick(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents")
        equity = pick(bs, "Stockholders Equity", "Common Stock Equity")
        revenue = pick(inc, "Total Revenue", "Operating Revenue")
        ebit = pick(inc, "Operating Income", "EBIT")
        net_income = pick(inc, "Net Income Common Stockholders", "Net Income")
        eps = pick(inc, "Diluted EPS")
        shares = pick(inc, "Diluted Average Shares")
        if eps is None:
            eps = divide(net_income, shares)
        fcf = pick(cf, "Free Cash Flow")
        ocf, capex = pick(cf, "Operating Cash Flow"), pick(cf, "Capital Expenditure")
        if fcf is None and ocf is not None and capex is not None:
            fcf = ocf - abs(capex)
        ebitda = pick(inc, "EBITDA", "Normalized EBITDA")
        if ebitda is None:
            depreciation = pick(inc, "Reconciled Depreciation")
            if depreciation is None:
                depreciation = pick(cf, "Depreciation Depletion And Amortization", "Depreciation And Amortization")
            if ebit is not None and depreciation is not None:
                ebitda = ebit + depreciation
        rows.append({"period_end": date, "revenue": revenue, "operating_income": ebit,
                     "net_income": net_income, "diluted_eps": eps, "diluted_shares": shares,
                     "free_cash_flow": fcf, "ebitda": ebitda, "debt": debt, "cash": cash,
                     "equity": equity, "capital": debt + equity if debt is not None and equity is not None else None,
                     "operating_margin_pct": divide(ebit, revenue, 100),
                     "fcf_margin_pct": divide(fcf, revenue, 100)})
    metrics = {key: None for key in ["operating_return_pct", "operating_margin_3y_pct",
              "fcf_margin_3y_pct", "fcf_positive_years_pct", "net_debt_to_ebitda",
              "revenue_cagr_pct", "eps_cagr_pct", "earnings_yield_pct", "fcf_yield_pct", "ebitda_yield_pct"]}
    result = {"annual_periods": rows, "annual_period_end": dates[0] if dates else None,
              "quality_window_start": None, "quality_window_years": None,
              "financial_currency": financial_currency,
              "currency_compatible": bool(quote_currency and financial_currency and quote_currency == financial_currency),
              "eps_growth_state": "missing", "leverage_state": "missing", "metric_notes": [], **metrics}
    if not rows:
        return result
    latest = rows[0]
    if len(rows) >= 2 and latest["capital"] is not None and rows[1]["capital"] is not None:
        gap = (pd.Timestamp(rows[0]["period_end"]) - pd.Timestamp(rows[1]["period_end"])).days
        if 300 <= gap <= 430:
            result["operating_return_pct"] = divide(latest["operating_income"], (latest["capital"] + rows[1]["capital"]) / 2, 100)
    if len(rows) >= 3:
        window = rows[:3]
        gaps = [(pd.Timestamp(window[i]["period_end"]) - pd.Timestamp(window[i+1]["period_end"])).days for i in (0, 1)]
        if all(300 <= gap <= 430 for gap in gaps):
            years = sum(gaps) / 365.25
            result.update(quality_window_start=window[-1]["period_end"], quality_window_years=round(years, 3))
            result["operating_margin_3y_pct"] = complete_median([r["operating_margin_pct"] for r in window])
            result["fcf_margin_3y_pct"] = complete_median([r["fcf_margin_pct"] for r in window])
            if all(r["free_cash_flow"] is not None for r in window):
                result["fcf_positive_years_pct"] = sum(r["free_cash_flow"] > 0 for r in window) / 3 * 100
            if all(r["revenue"] is not None and r["revenue"] > 0 for r in window):
                result["revenue_cagr_pct"] = ((latest["revenue"] / window[-1]["revenue"]) ** (1 / years) - 1) * 100
            if all(r["diluted_eps"] is not None for r in window):
                if all(r["diluted_eps"] > 0 for r in window):
                    result["eps_cagr_pct"] = ((latest["diluted_eps"] / window[-1]["diluted_eps"]) ** (1 / years) - 1) * 100
                    result["eps_growth_state"] = "positive_history"
                else:
                    result["eps_growth_state"] = "nonpositive_history"
                    result["metric_notes"].append("EPS was nonpositive in at least one of the three fiscal years; the growth factor earns zero. A loss recovery is not treated as a positive-base CAGR.")
    if all(latest[k] is not None for k in ["debt", "cash", "ebitda"]):
        net_debt = latest["debt"] - latest["cash"]
        if latest["ebitda"] > 0:
            result["net_debt_to_ebitda"] = net_debt / latest["ebitda"]
            result["leverage_state"] = "ratio_available"
        else:
            result["leverage_state"] = "nonpositive_ebitda"
            result["metric_notes"].append("Annual EBITDA is nonpositive; the debt-coverage factor earns zero.")
        enterprise_value = market_cap + net_debt if market_cap is not None else None
    else:
        enterprise_value = None
    result["simplified_enterprise_value"] = enterprise_value
    if result["currency_compatible"]:
        result["earnings_yield_pct"] = divide(latest["net_income"], market_cap, 100)
        result["fcf_yield_pct"] = divide(latest["free_cash_flow"], market_cap, 100)
        result["ebitda_yield_pct"] = divide(latest["ebitda"], enterprise_value, 100)
    else:
        result["metric_notes"].append("Financial and quote currencies are unavailable or different; valuation is withheld without an FX conversion.")
    return result
