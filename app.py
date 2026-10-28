from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote_plus
import math
import os
import time
import secrets
import hmac
import hashlib
import requests
import pandas as pd
import yfinance as yf
from flask import Flask, render_template, request, jsonify
from scoring import evaluate, utcnow, QUALITY, OPPORTUNITY
from recommendations import load_snapshot, saved_report, page_data, is_stale
from financials import extract_annual
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash
from submissions import bp as submissions_bp


app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
production = os.getenv("THESIS_ENV") == "production" or bool(os.getenv("RAILWAY_ENVIRONMENT_NAME"))
secret_key = os.getenv("SECRET_KEY", "")
admin_password = os.getenv("ADMIN_PASSWORD", "")
app.config.update(PRODUCTION=production,
    SECRET_KEY=secret_key if len(secret_key) >= 32 else (None if production else secrets.token_hex(32)),
    DATABASE_URL=os.getenv("DATABASE_URL", ""),
    SUGGESTIONS_DB_PATH=os.getenv("SUGGESTIONS_DB_PATH", os.path.join(app.instance_path, "suggestions.sqlite3")),
    ADMIN_PASSWORD_HASH=generate_password_hash(admin_password) if len(admin_password) >= 16 else "",
    ADMIN_AUTH_VERSION=hmac.new(secret_key.encode(), admin_password.encode(), hashlib.sha256).hexdigest(),
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=production,
    MAX_CONTENT_LENGTH=16384)
if production:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.register_blueprint(submissions_bp)

APP_VERSION = "1.3"
LAST_REVIEWED = "October 28, 2026"
REPORT_CACHE_TTL_SECONDS = 300
REPORT_CACHE: dict[str, tuple[float, dict]] = {}
SUGGESTION_CACHE: dict[str, tuple[float, list[dict]]] = {}


COMPANY_ALIASES = [
    {
        "ticker": "MOD",
        "name": "Modine Manufacturing",
        "category": "Data center cooling",
    },
    {
        "ticker": "IESC",
        "name": "IES Holdings",
        "category": "Electrical infrastructure",
    },
    {
        "ticker": "ACLS",
        "name": "Axcelis Technologies",
        "category": "Semiconductor equipment",
    },
    {
        "ticker": "POWL",
        "name": "Powell Industries",
        "category": "Power grid equipment",
    },
    {
        "ticker": "ONTO",
        "name": "Onto Innovation",
        "category": "Semiconductor inspection",
    },
    {
        "ticker": "NVMI",
        "name": "Nova Ltd.",
        "category": "Semiconductor metrology",
    },
    {
        "ticker": "AMKR",
        "name": "Amkor Technology",
        "category": "Advanced chip packaging",
    },
    {
        "ticker": "TMDX",
        "name": "TransMedics Group",
        "category": "Medical technology",
    },
    {
        "ticker": "MYRG",
        "name": "MYR Group",
        "category": "Electrical construction",
    },
    {
        "ticker": "FLR",
        "name": "Fluor",
        "category": "Engineering and construction",
    },
]


def clean_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def pct(value: Optional[float]) -> Optional[float]:
    return None if value is None else value * 100


def growth_rate(latest: Optional[float], previous: Optional[float]) -> Optional[float]:
    if latest is None or previous in (None, 0):
        return None
    return (latest - previous) / abs(previous)


def normalize_company_name(value: str) -> str:
    cleaned = value.lower().strip()
    cleaned = cleaned.replace("&", "and")
    cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", "")
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.replace("’", "")
    cleaned = cleaned.replace("-", " ")
    cleaned = " ".join(cleaned.split())

    endings = [
        " corporation", " corp", " incorporated", " inc",
        " company", " co", " ltd", " limited", " plc",
        " group", " holdings", " holding", " technologies", " technology",
    ]

    changed = True
    while changed:
        changed = False
        for ending in endings:
            if cleaned.endswith(ending):
                cleaned = cleaned[: -len(ending)].strip()
                changed = True
    return cleaned


def top_opportunity_aliases() -> dict:
    aliases = {}
    custom_aliases = {
        "MOD": ["Modine", "Modine Manufacturing", "Modine Manufacturing Company", "Modine Manufacturing Co"],
        "IESC": ["IES", "IES Holdings", "IES Holdings Inc"],
        "ACLS": ["Axcelis", "Axcelis Technologies", "Axcelis Technologies Inc"],
        "POWL": ["Powell", "Powell Industries", "Powell Industries Inc"],
        "ONTO": ["Onto", "Onto Innovation", "Onto Innovation Inc"],
        "NVMI": ["Nova", "Nova Ltd", "Nova Ltd."],
        "AMKR": ["Amkor", "Amkor Technology", "Amkor Technology Inc"],
        "TMDX": ["TransMedics", "TransMedics Group", "TransMedics Group Inc"],
        "MYRG": ["MYR", "MYR Group", "MYR Group Inc"],
        "FLR": ["Fluor", "Fluor Corporation", "Fluor Corp"],
    }

    for item in COMPANY_ALIASES:
        ticker = item["ticker"].upper()
        possible_names = {item["name"]}
        possible_names.update(custom_aliases.get(ticker, []))

        for possible in possible_names:
            aliases[normalize_company_name(possible)] = ticker

    return aliases


def resolve_known_company(query: str) -> str | None:
    q = query.strip()
    if not q:
        return None

    q_upper = q.upper()
    for item in COMPANY_ALIASES:
        if q_upper == item["ticker"].upper():
            return item["ticker"].upper()

    return top_opportunity_aliases().get(normalize_company_name(q))


def get_info(ticker: yf.Ticker) -> dict:
    try:
        info = ticker.get_info()
        return info if isinstance(info, dict) else {}
    except Exception:
        try:
            return ticker.info if isinstance(ticker.info, dict) else {}
        except Exception:
            return {}


def get_df_row(df: pd.DataFrame, possible_names: list[str]) -> list[float]:
    if df is None or df.empty:
        return []

    normalized = {str(idx).strip().lower(): idx for idx in df.index}

    for name in possible_names:
        key = name.strip().lower()
        if key in normalized:
            series = df.loc[normalized[key]]
            return [clean_number(x) for x in series.tolist()]

    for row_name in df.index:
        row_lower = str(row_name).strip().lower()
        for name in possible_names:
            if name.strip().lower() in row_lower:
                series = df.loc[row_name]
                return [clean_number(x) for x in series.tolist()]

    return []


def get_cached_suggestions(query: str) -> list[dict]:
    key = query.strip().lower()
    now = time.time()
    cached = SUGGESTION_CACHE.get(key)
    if cached and now - cached[0] < REPORT_CACHE_TTL_SECONDS:
        return cached[1]

    suggestions = lookup_company_suggestions(query)
    SUGGESTION_CACHE[key] = (now, suggestions)
    return suggestions


def lookup_company_suggestions(query: str) -> list[dict]:
    q = query.strip()
    if len(q) < 2:
        return []

    results = []
    seen = set()

    def add_result(name, symbol=None):
        if not name:
            return
        clean_name = str(name).strip()
        key = clean_name.lower()
        if key in seen:
            return
        seen.add(key)
        results.append({"name": clean_name, "symbol": symbol or ""})

    for item in COMPANY_ALIASES:
        name = item["name"]
        ticker = item["ticker"]
        normalized_name = normalize_company_name(name)
        normalized_q = normalize_company_name(q)
        if normalized_name.startswith(normalized_q) or normalized_q in normalized_name:
            add_result(name, ticker)

    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {"q": q, "quotesCount": 10, "newsCount": 0}
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        quotes = data.get("quotes", [])

        for item in quotes:
            if item.get("quoteType") not in {"EQUITY", "ETF"}:
                continue
            name = item.get("longname") or item.get("shortname")
            if name and name.lower().startswith(q.lower()):
                add_result(name, item.get("symbol"))

        for item in quotes:
            if len(results) >= 8:
                break
            if item.get("quoteType") not in {"EQUITY", "ETF"}:
                continue
            name = item.get("longname") or item.get("shortname")
            if name and q.lower() in name.lower():
                add_result(name, item.get("symbol"))
    except Exception:
        pass

    return results[:8]


def lookup_symbol(query: str) -> tuple[str, Optional[str]]:
    q = query.strip()
    if not q:
        raise ValueError("Enter a company name or ticker.")

    known_symbol = resolve_known_company(q)
    if known_symbol:
        matching_name = next(
            (item["name"] for item in COMPANY_ALIASES if item["ticker"].upper() == known_symbol),
            None,
        )
        return known_symbol, matching_name

    # Treat short ALL-CAPS inputs as tickers. Mixed-case words such as "Apple"
    # are resolved as company names instead of becoming the invalid ticker APPLE.
    is_probable_ticker = (
        " " not in q
        and len(q) <= 6
        and q.upper() == q
        and q.replace(".", "").replace("-", "").isalnum()
    )
    if is_probable_ticker:
        return q.upper(), None

    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {"q": q, "quotesCount": 8, "newsCount": 0}
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("quotes", []):
            if item.get("symbol") and item.get("quoteType") in {"EQUITY", "ETF"}:
                return item["symbol"].upper(), item.get("shortname") or item.get("longname")
    except Exception:
        pass

    return q.upper(), None


def build_source_links(symbol: str, name: str, website: str | None = None) -> list[dict]:
    encoded_name = quote_plus(name)
    links = [
        {
            "label": "Yahoo Finance company page",
            "url": f"https://finance.yahoo.com/quote/{symbol}",
            "type": "Market data",
            "covers": "Price, market capitalization, valuation ratios, growth, margins, analyst targets, and historical market data used by the current prototype.",
        },
        {
            "label": "SEC EDGAR company filings",
            "url": f"https://www.sec.gov/edgar/browse/?CIK={symbol}&owner=exclude&action=getcompany",
            "type": "Primary source",
            "covers": "10-K annual reports, 10-Q quarterly reports, 8-K current reports, and other official company filings.",
        },
        {
            "label": "SEC company search",
            "url": f"https://www.sec.gov/edgar/search/#/q={encoded_name}",
            "type": "Primary source",
            "covers": "Alternative SEC search by company name if ticker lookup does not resolve correctly.",
        },
        {
            "label": "Thesis methodology",
            "url": "/methodology",
            "type": "Calculation reference",
            "covers": "How Thesis converts financial and market inputs into Business Quality, Opportunity, and Would We Invest? outputs.",
        },
    ]
    if website:
        links.insert(1, {
            "label": "Official company website",
            "url": website,
            "type": "Company source",
            "covers": "Corporate information, products, investor materials, earnings releases, and management commentary when available.",
        })
    return links


def get_cached_report(query: str) -> dict:
    snapshot_report = saved_report(resolve_known_company(query) or query)
    if snapshot_report:
        return snapshot_report
    key = query.strip().upper()
    now = time.time()
    cached = REPORT_CACHE.get(key)
    if cached and now - cached[0] < REPORT_CACHE_TTL_SECONDS:
        return cached[1]

    report = build_report(query)
    REPORT_CACHE[key] = (now, report)
    return report


def build_report(query: str) -> dict:
    symbol, lookup_name = lookup_symbol(query)
    ticker = yf.Ticker(symbol)
    info = get_info(ticker)

    try:
        history = ticker.history(period="1y", auto_adjust=True)
    except Exception:
        history = pd.DataFrame()

    if (history is None or history.empty) and not info:
        raise ValueError(f"No usable market data found for '{query}'.")

    try:
        financials = ticker.financials
    except Exception:
        financials = pd.DataFrame()

    try:
        cashflow = ticker.cashflow
    except Exception:
        cashflow = pd.DataFrame()

    try:
        balance = ticker.balance_sheet
    except Exception:
        balance = pd.DataFrame()

    name = info.get("longName") or info.get("shortName") or lookup_name or symbol
    sector = info.get("sector") or "Unknown sector"
    industry = info.get("industry") or "Unknown industry"
    website = info.get("website")
    exchange = info.get("exchange") or info.get("fullExchangeName") or "Unknown exchange"

    price = clean_number(info.get("regularMarketPrice"))
    if price is None and history is not None and not history.empty:
        price = clean_number(history["Close"].dropna().iloc[-1])

    previous_close = clean_number(info.get("previousClose"))
    day_change_pct = pct(growth_rate(price, previous_close)) if price is not None and previous_close else None

    market_cap = clean_number(info.get("marketCap"))
    trailing_pe = clean_number(info.get("trailingPE"))
    forward_pe = clean_number(info.get("forwardPE"))
    peg = clean_number(info.get("pegRatio"))
    beta = clean_number(info.get("beta"))
    target_mean = clean_number(info.get("targetMeanPrice"))

    profit_margin = clean_number(info.get("profitMargins"))
    roe = clean_number(info.get("returnOnEquity"))
    debt_to_equity = clean_number(info.get("debtToEquity"))
    revenue_growth = clean_number(info.get("revenueGrowth"))
    earnings_growth = clean_number(info.get("earningsGrowth"))

    revenue_values = get_df_row(financials, ["Total Revenue", "Operating Revenue"])
    net_income_values = get_df_row(financials, ["Net Income", "Net Income Common Stockholders"])
    fcf_values = get_df_row(cashflow, ["Free Cash Flow"])
    operating_cf_values = get_df_row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    capex_values = get_df_row(cashflow, ["Capital Expenditure", "Capital Expenditures"])

    if revenue_growth is None and len(revenue_values) >= 2:
        revenue_growth = growth_rate(revenue_values[0], revenue_values[1])

    if earnings_growth is None and len(net_income_values) >= 2:
        earnings_growth = growth_rate(net_income_values[0], net_income_values[1])

    latest_fcf = fcf_values[0] if fcf_values else None
    previous_fcf = fcf_values[1] if len(fcf_values) >= 2 else None

    if latest_fcf is None and operating_cf_values:
        latest_ocf = operating_cf_values[0]
        latest_capex = capex_values[0] if capex_values else None
        if latest_ocf is not None and latest_capex is not None:
            latest_fcf = latest_ocf - abs(latest_capex)

    fcf_growth = growth_rate(latest_fcf, previous_fcf)

    target_upside = growth_rate(target_mean, price) if target_mean is not None and price else None
    def period_end(frame):
        try:
            return pd.Timestamp(frame.columns[0]).isoformat() if not frame.empty else None
        except (ValueError, TypeError):
            return None
    market_date = None
    momentum = None
    if history is not None and not history.empty:
        closes = history["Close"].dropna()
        if isinstance(history.index, pd.DatetimeIndex):
            market_date = history.index[-1].isoformat()
        if len(closes) >= 127:
            momentum = pct(growth_rate(float(closes.iloc[-1]), float(closes.iloc[-127])))
    report = {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "industry": industry,
        "exchange": exchange,
        "website": website,
        "sources": build_source_links(symbol, name, website),
        "price": price,
        "day_change_pct": day_change_pct,
        "market_cap": market_cap,
        "trailing_pe": trailing_pe,
        "forward_pe": forward_pe,
        "peg": peg,
        "beta": beta,
        "target_mean": target_mean,
        "target_upside_pct": pct(target_upside) if target_upside is not None else None,
        "revenue_growth_pct": pct(revenue_growth) if revenue_growth is not None else None,
        "earnings_growth_pct": pct(earnings_growth) if earnings_growth is not None else None,
        "profit_margin_pct": pct(profit_margin) if profit_margin is not None else None,
        "roe_pct": pct(roe) if roe is not None else None,
        "free_cash_flow": latest_fcf,
        "debt_to_equity": debt_to_equity,
        "momentum_pct": momentum,
        "currency": info.get("currency") or "reported currency",
        "business_summary": info.get("longBusinessSummary"),
        "market_data_as_of": market_date,
        "financial_period_end": period_end(financials),
        "cashflow_period_end": period_end(cashflow),
        "retrieved_at": utcnow().isoformat(),
        "editorial_reviewed_at": None,
        "change_opinion": ["Changes in the displayed financial inputs or price can change this screen.",
                           "A company-specific investment thesis must be checked against filings."],
        "app_version": APP_VERSION,
        "last_reviewed": LAST_REVIEWED,
        "data_warning": "Quantitative research estimates from Yahoo Finance via yfinance; not a validated return prediction. Verify figures against company filings before making an investment decision.",
    }

    report.update(extract_annual(financials, cashflow, balance, market_cap,
                                 info.get("currency"), info.get("financialCurrency")))
    snapshot = load_snapshot()
    peers = snapshot["reports"] if snapshot and not is_stale(snapshot) else None
    return evaluate(report, peers=peers)


@app.template_filter("fmt_money")
def fmt_money(value, currency="USD"):
    value = clean_number(value)
    if value is None:
        return "N/A"
    prefix = "$" if currency == "USD" else f"{currency} "
    abs_v = abs(value)
    if abs_v >= 1_000_000_000_000:
        return f"{prefix}{value/1_000_000_000_000:.2f}T"
    if abs_v >= 1_000_000_000:
        return f"{prefix}{value/1_000_000_000:.2f}B"
    if abs_v >= 1_000_000:
        return f"{prefix}{value/1_000_000:.2f}M"
    return f"{prefix}{value:,.2f}"


@app.template_filter("fmt_num")
def fmt_num(value):
    value = clean_number(value)
    return "N/A" if value is None else f"{value:,.2f}"


@app.template_filter("fmt_pct")
def fmt_pct(value):
    value = clean_number(value)
    return "N/A" if value is None else f"{value:+.2f}%"


@app.template_filter("date_label")
def date_label(value):
    from datetime import datetime, timezone
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    except (ValueError, TypeError, AttributeError):
        return 'Unavailable'


@app.route("/top-opportunities")
def top_opportunities():
    version = request.args.get("snapshot")
    try:
        snapshot = load_snapshot(version)
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        return "Invalid page or snapshot.", 400
    if version and not snapshot:
        return "This snapshot is unavailable. Open /top-opportunities to restart.", 410
    sector = request.args.get("sector", "")
    size = request.args.get("size", "")
    if size not in ("", "small", "mid", "large"):
        return "Invalid size filter.", 400
    try:
        data = page_data(snapshot, page, sector, size, request.args.get("view", "all"), request.args.get("sort", "combined"))
    except ValueError:
        return "Invalid research filter.", 400
    return render_template("top_opportunities.html", **data)


@app.route("/discover")
def discover():
    try:
        snapshot = load_snapshot(request.args.get("snapshot"))
        page = max(1, int(request.args.get("page", "1")))
        minimum = int(request.args.get("minimum_quality", "0"))
        if minimum not in (0, 60, 70, 80):
            raise ValueError("Invalid quality preference")
        data = page_data(snapshot, page, request.args.get("sector", ""), request.args.get("size", ""),
                         "all", request.args.get("sort", "combined"), minimum)
    except ValueError:
        return "Invalid research preference.", 400
    if request.args.get("snapshot") and not snapshot:
        return "This snapshot is unavailable. Open /discover to restart.", 410
    return render_template("discover.html", **data, searched=bool(request.args))


@app.route("/api/suggest")
def suggest():
    query = request.args.get("q", "")
    if len(query.strip()) < 2:
        return jsonify([])
    return jsonify(get_cached_suggestions(query))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": APP_VERSION})


@app.route("/data-status")
def data_status():
    snapshot = load_snapshot()
    if not snapshot:
        return jsonify({"status": "missing", "version": APP_VERSION}), 503
    stale = is_stale(snapshot)
    return jsonify({"status": "stale" if stale else "ready", "version": APP_VERSION,
                    "snapshot_id": snapshot["id"], "generated_at": snapshot["generated_at"],
                    "universe_count": snapshot["universe_count"],
                    "fetched_count": snapshot["fetched_count"],
                    "complete_count": snapshot["complete_count"],
                    "model_version": snapshot["model_version"],
                    "rated_count": len(snapshot.get("rankings", [])),
                    "quality_count": snapshot.get("quality_count", 0),
                    "opportunity_count": snapshot.get("opportunity_count", 0),
                    "recommendation_count": len(snapshot["recommendations"])}), 503 if stale else 200



@app.route("/sources/<symbol>")
def company_sources(symbol):
    try:
        version = request.args.get("snapshot")
        report = saved_report(symbol.upper(), version) if version else get_cached_report(symbol.upper())
        if not report:
            return "Report snapshot unavailable. Open /top-opportunities to restart.", 410
        return render_template("sources.html", report=report)
    except Exception as exc:
        return render_template("sources.html", report=None, error=f"Sources could not be loaded: {exc}", symbol=symbol.upper()), 404

@app.route("/methodology")
def methodology():
    return render_template("methodology.html", last_reviewed=LAST_REVIEWED, quality=QUALITY, opportunity=OPPORTUNITY)


@app.route("/disclosures")
def disclosures():
    return render_template("disclosures.html", last_reviewed=LAST_REVIEWED)


@app.route("/")
def home():
    return render_template("index.html", report=None, error=None, query="")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return render_template("index.html", report=None, error="Enter a company name or ticker.", query=query)

    try:
        version = request.args.get("snapshot")
        if version:
            report = saved_report(resolve_known_company(query) or query, version)
            if not report:
                return "Report snapshot unavailable. Open /top-opportunities to restart.", 410
        else:
            report = get_cached_report(query)
        return render_template("index.html", report=report, error=None, query=query)
    except Exception as exc:
        return render_template("index.html", report=None, error="Market data is unavailable. Please try again later.", query=query)


@app.route("/how-to-invest")
def how_to_invest():
    return render_template("how_to_invest.html")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG") == "1",
    )
