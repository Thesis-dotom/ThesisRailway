"""Regression coverage for name searches, provider outages and stalled reports."""
import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import app
import recommendations as rec
import refresh_recommendations as refresh
from company_lookup import normalize_company_name, resolve_company
from scoring import utcnow
from refresh_company_directory import make_directory, refresh_directory


@pytest.fixture(autouse=True)
def clean_caches():
    app.REPORT_CACHE.clear()
    app.SUGGESTION_CACHE.clear()
    yield
    app.REPORT_CACHE.clear()
    app.SUGGESTION_CACHE.clear()


def unexpected(*args, **kwargs):
    raise AssertionError("Saved company searches must not request live data")


@pytest.mark.parametrize("query,symbol", [
    ("Microsoft", "MSFT"), ("MICROSOFT", "MSFT"), ("Microsoft Corp.", "MSFT"),
    ("msft", "MSFT"), ("$MSFT", "MSFT"), ("Home Depot", "HD"),
    ("Caterpillar", "CAT"), ("Modine", "MOD"), ("Johnson & Johnson", "JNJ"),
    ("D.R. Horton", "DHI"), ("Moog", "MOG-A"), ("mog.a", "MOG-A"),
])
def test_saved_company_names_work_without_provider(monkeypatch, query, symbol):
    monkeypatch.setattr(app, "provider_search", unexpected)
    monkeypatch.setattr(app, "build_live_report", unexpected)
    report = app.get_cached_report(query)
    assert report["symbol"] == symbol
    assert report["snapshot_id"] == rec.load_snapshot()["id"]
    response = app.app.test_client().get("/search", query_string={"q": query})
    assert response.status_code == 200
    assert f'<span class="ticker-pill">{symbol}</span>'.encode() in response.data


def test_all_saved_companies_accept_full_and_normalized_names(monkeypatch):
    monkeypatch.setattr(app, "provider_search", unexpected)
    monkeypatch.setattr(app, "build_live_report", unexpected)
    for symbol, saved in rec.load_snapshot()["reports"].items():
        for query in (saved["name"], normalize_company_name(saved["name"]), symbol.lower()):
            report = app.get_cached_report(query)
            assert report["symbol"] == symbol, query
            assert report["business_quality"] == saved["business_quality"]
            assert report["opportunity"] == saved["opportunity"]


@pytest.mark.parametrize("query,symbol", [("Mic", "MSFT"), ("msft", "MSFT"),
                                         ("Nvi", "NVDA"), ("App", "AAPL"),
                                         ("G", "G"), ("Modine", "MOD")])
def test_autocomplete_works_without_provider(monkeypatch, query, symbol):
    monkeypatch.setattr(app, "provider_search", unexpected)
    response = app.app.test_client().get("/api/suggest", query_string={"q": query})
    assert response.status_code == 200
    assert any(item["symbol"] == symbol for item in response.json)
    symbols = [item["symbol"] for item in response.json]
    assert len(symbols) == len(set(symbols))


@pytest.mark.parametrize("query,symbol", [("Apple", "AAPL"), ("APPLE", "AAPL"),
                                         ("nvidia", "NVDA"), ("Tesla", "TSLA"),
                                         ("Google", "GOOGL")])
def test_common_live_company_names_resolve_without_name_service(monkeypatch, query, symbol):
    monkeypatch.setattr(app, "provider_search", unexpected)
    calls = []
    def fetch(ticker):
        calls.append(ticker)
        return {"symbol": ticker}
    monkeypatch.setattr(app, "build_live_report", fetch)
    assert app.get_cached_report(query)["symbol"] == symbol
    assert app.get_cached_report(symbol.lower())["symbol"] == symbol
    assert calls == [symbol]  # Both names share the same ticker-keyed cache.


def test_remote_lookup_reuses_saved_report(monkeypatch):
    monkeypatch.setattr(app.yf, "Search", lambda *a, **k: SimpleNamespace(
        quotes=[{"symbol": "MSFT", "quoteType": "EQUITY", "longname": "Microsoft Corporation"}]))
    monkeypatch.setattr(app, "build_live_report", unexpected)
    assert app.get_cached_report("Microsoft software company")["symbol"] == "MSFT"


def test_unknown_name_is_not_fabricated_as_ticker(monkeypatch):
    monkeypatch.setattr(app, "provider_search", lambda _: [])
    monkeypatch.setattr(app, "build_live_report", unexpected)
    response = app.app.test_client().get("/search?q=No+Such+Company")
    assert response.status_code == 400
    assert b"No matching company" in response.data
    assert b'role="alert"' in response.data


def test_remote_search_filters_invalid_instruments(monkeypatch):
    monkeypatch.setattr(app.yf, "Search", lambda *a, **k: SimpleNamespace(quotes=[
        {"symbol": "EXAMPLE=F", "quoteType": "FUTURE"},
        {"symbol": "EXM", "quoteType": "EQUITY", "longname": "Example Holdings"},
        {"symbol": "EXM", "quoteType": "EQUITY", "shortname": "Example"},
    ]))
    assert app.lookup_company_suggestions("Example") == [{"symbol": "EXM", "name": "Example Holdings"}]


def test_failed_report_returns_actionable_error_and_releases_slot(monkeypatch):
    paths = []
    def timeout(symbol, limit, output, delay):
        assert limit == 30
        paths.append(output)
        return {"report": None, "error_type": "TimeoutExpired"}
    monkeypatch.setattr(refresh, "fetch_company", timeout)
    response = app.app.test_client().get("/search?q=Apple")
    assert response.status_code == 503
    assert b"Saved reports in Top Opportunities are still available" in response.data
    assert b"TimeoutExpired" not in response.data
    assert not paths[0].parent.exists()
    assert not app.REPORT_CACHE
    monkeypatch.setattr(refresh, "fetch_company", lambda *a: {"report": {"symbol": "AAPL"}})
    assert app.build_live_report("AAPL")["symbol"] == "AAPL"


def test_slow_live_report_does_not_block_saved_searches(monkeypatch):
    started, finish = threading.Event(), threading.Event()
    def slow(*args):
        started.set()
        assert finish.wait(timeout=3)
        return {"report": {"symbol": "AAPL"}}
    monkeypatch.setattr(refresh, "fetch_company", slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(app.build_live_report, "AAPL")
        assert started.wait(timeout=2)
        try:
            client = app.app.test_client()
            assert client.get("/search?q=Microsoft").status_code == 200
            busy = client.get("/search?q=Nvidia")
            assert busy.status_code == 503 and b"Another live report" in busy.data
        finally:
            finish.set()
        assert future.result(timeout=2)["symbol"] == "AAPL"


def test_historical_names_use_requested_snapshot(tmp_path, monkeypatch):
    old = copy.deepcopy(rec.load_snapshot())
    old["reports"]["MSFT"]["name"] = "Original Company Corporation"
    old["generated_at"] = (utcnow() - timedelta(days=9)).isoformat()
    current = copy.deepcopy(old)
    current["id"] = "20261029T120000-0000"
    current["reports"]["MSFT"]["name"] = "Renamed Company Corporation"
    refresh.atomic_write(tmp_path / "recommendations.json", current)
    refresh.atomic_write(tmp_path / "history" / (old["id"] + ".json"), old)
    monkeypatch.setattr(rec, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "build_live_report", unexpected)
    response = app.app.test_client().get("/search", query_string={"q": "Original Company", "snapshot": old["id"]})
    assert response.status_code == 200
    assert b"Original Company Corporation" in response.data
    assert b"Historical snapshot" in response.data


def test_ambiguous_name_does_not_pick_arbitrary_company():
    assert resolve_company("Example", [{"symbol": "AAA", "name": "Example Inc."},
                                       {"symbol": "BBB", "name": "Example Corporation"}]) is None


def test_overlong_queries_do_not_reach_provider(monkeypatch):
    monkeypatch.setattr(app, "provider_search", unexpected)
    client = app.app.test_client()
    assert client.get("/search", query_string={"q": "A" * 101}).status_code == 400
    assert client.get("/api/suggest", query_string={"q": "A" * 101}).json == []


@pytest.mark.parametrize("query,symbol", [("Spotify", "SPOT"), ("Roku", "ROKU"),
                                         ("Costco", "COST"), ("Palantir", "PLTR"),
                                         ("SentinelOne", "S"), ("Snowflake", "SNOW")])
def test_broader_company_directory_avoids_provider_name_search(monkeypatch, query, symbol):
    monkeypatch.setattr(app, "provider_search", unexpected)
    assert app.lookup_symbol(query)[0] == symbol
    assert any(item["symbol"] == symbol for item in app.lookup_company_suggestions(query))


def test_directory_rejects_truncated_download():
    with pytest.raises(ValueError, match="Incomplete"):
        make_directory({"0": {"ticker": "SPOT", "title": "Spotify Technology S.A."}})


def test_failed_directory_download_preserves_previous_file(tmp_path):
    path = tmp_path / "company_directory.json"
    path.write_text('{"companies": []}')
    original = path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError("download failed")
    with pytest.raises(OSError):
        refresh_directory(path, fetch=fail)
    assert path.read_bytes() == original


def test_directory_does_not_publish_unexpected_coverage_drop(tmp_path):
    path = tmp_path / "company_directory.json"
    refresh.atomic_write(path, {"companies": [{"symbol": str(i)} for i in range(2000)]})
    original = path.read_bytes()
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
        str(i): {"ticker": f"ZZ{i}", "title": f"Company {i}"} for i in range(1000)})
    with pytest.raises(ValueError, match="shrank"):
        refresh_directory(path, fetch=lambda *a, **k: response)
    assert path.read_bytes() == original


def test_directory_success_publishes_names_without_scores(tmp_path):
    path = tmp_path / "company_directory.json"
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
        str(i): {"ticker": f"ZZ{i}", "title": f"Company {i}"} for i in range(1000)})
    assert refresh_directory(path, fetch=lambda *a, **k: response) == 1000
    import json
    saved = json.loads(path.read_text())
    assert saved["source"] == "https://www.sec.gov/files/company_tickers.json"
    assert all(set(item) == {"symbol", "name"} for item in saved["companies"])
