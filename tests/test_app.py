
import pandas as pd
import app as thesis


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol
        self.financials = pd.DataFrame()
        self.cashflow = pd.DataFrame()

    def get_info(self):
        return {
            "longName": "Example Corporation",
            "sector": "Technology",
            "industry": "Software",
            "regularMarketPrice": 100,
            "previousClose": 98,
            "marketCap": 10_000_000_000,
            "trailingPE": 24,
            "forwardPE": 20,
            "pegRatio": 1.5,
            "beta": 1.1,
            "targetMeanPrice": 120,
            "profitMargins": 0.18,
            "returnOnEquity": 0.20,
            "debtToEquity": 40,
            "revenueGrowth": 0.15,
            "earningsGrowth": 0.12,
        }

    def history(self, period="1y", auto_adjust=True):
        return pd.DataFrame({"Close": [80 + i * 0.1 for i in range(260)]})


def test_static_routes():
    client = thesis.app.test_client()
    for route in ["/", "/how-to-invest", "/top-opportunities", "/methodology", "/disclosures", "/health"]:
        response = client.get(route)
        assert response.status_code == 200


def test_company_report(monkeypatch):
    monkeypatch.setattr(thesis.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(thesis, "build_live_report", thesis.build_report)
    thesis.REPORT_CACHE.clear()
    client = thesis.app.test_client()
    response = client.get("/search?q=AAPL")
    assert response.status_code == 200
    assert b"Example Corporation" in response.data
    assert b"Business Quality Rating" in response.data
    assert b"Opportunity Rating" in response.data


def test_top_opportunity_name_mapping():
    assert thesis.resolve_known_company("Modine Manufacturing") == "MOD"
    assert thesis.resolve_known_company("MOD") == "MOD"


def test_company_word_not_forced_to_ticker(monkeypatch):
    monkeypatch.setattr(thesis, "provider_search", lambda *_: (_ for _ in ()).throw(AssertionError("Apple should resolve locally")))
    symbol, _ = thesis.lookup_symbol("Apple")
    assert symbol == "AAPL"
