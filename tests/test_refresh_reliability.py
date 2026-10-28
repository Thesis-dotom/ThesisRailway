import copy
from datetime import timedelta
from types import SimpleNamespace

import pytest

import app
import recommendations
from provider_diagnostics import ProviderDiagnostics
from refresh_recommendations import collect_reports, finish_refresh, atomic_write, publish
from scoring import utcnow
from test_refresh import report


def result(value=None, **extra):
    return {"report": value, "requests": [], "rate_limited": False, **extra}


def test_retry_only_incomplete_company_and_save_progress():
    calls, checkpoints = [], []
    incomplete = report("B")
    incomplete["fcf_margin_3y_pct"] = None
    def fetch(symbol, timeout):
        calls.append(symbol)
        return result(incomplete if calls.count(symbol) == 1 and symbol == "B" else report(symbol))
    reports, status = collect_reports(["A", "B"], fetch, sleep=lambda _: None,
                                     checkpoint=lambda r, s: checkpoints.append(copy.deepcopy(s)))
    assert calls == ["A", "B", "B"]
    assert all(r["eligible_data"] for r in reports.values())
    assert status["raw_complete_count"] == 2
    assert checkpoints[1]["attempts"]["B"][0]["missing_data"] == ["Three-year free-cash-flow margin"]


def test_partial_attempts_are_never_combined_into_complete_data():
    first, second = report("A"), report("A")
    first["fcf_margin_3y_pct"] = None
    second["earnings_yield_pct"] = None
    responses = iter([first, second])
    reports, _ = collect_reports(["A"], lambda *_: result(next(responses)), sleep=lambda _: None)
    assert not reports["A"]["eligible_data"]
    assert reports["A"]["missing_data"] == ["Annual earnings yield"]


def test_rate_limit_stops_collection_and_preserves_published_snapshot(tmp_path):
    old = publish({"A": report("A")}, ["A"])
    path = tmp_path / "recommendations.json"
    atomic_write(path, old)
    original = path.read_bytes()
    calls = []
    def fetch(symbol, timeout):
        calls.append(symbol)
        return result(report(symbol), rate_limited=True)
    reports, status = collect_reports(["A", "B"], fetch, sleep=lambda _: None)
    assert calls == ["A"]
    assert finish_refresh(reports, ["A", "B"], status, tmp_path, old) is None
    assert status["state"] == "failed"
    assert path.read_bytes() == original
    assert not (tmp_path / "history").exists()


def test_coverage_failure_preserves_snapshot_after_real_collection(tmp_path):
    old = publish({"A": report("A")}, ["A"])
    path = tmp_path / "recommendations.json"
    atomic_write(path, old)
    original = path.read_bytes()
    incomplete = report("A")
    incomplete["fcf_margin_3y_pct"] = None
    reports, status = collect_reports(["A"], lambda *_: result(incomplete), sleep=lambda _: None)
    assert finish_refresh(reports, ["A"], status, tmp_path, old) is None
    assert "60%" in status["reason"]
    assert path.read_bytes() == original


def test_success_publishes_current_and_history(tmp_path):
    universe = [f'T{i}' for i in range(10)]
    reports, status = collect_reports(universe, lambda symbol, _: result(report(symbol)), sleep=lambda _: None)
    snapshot = finish_refresh(reports, universe, status, tmp_path)
    assert status["state"] == "published"
    assert (tmp_path / "recommendations.json").read_bytes() == (tmp_path / "history" / (snapshot["id"] + ".json")).read_bytes()


def test_history_write_failure_does_not_replace_current_snapshot(tmp_path, monkeypatch):
    import refresh_recommendations as refresh
    old = publish({"A": report("A")}, ["A"])
    path = tmp_path / "recommendations.json"
    atomic_write(path, old)
    original = path.read_bytes()
    def no_space(*_):
        raise OSError("disk full")
    monkeypatch.setattr(refresh, "atomic_write", no_space)
    status = {}
    reports = {f'T{i}': report(f'T{i}') for i in range(10)}
    assert finish_refresh(reports, list(reports), status, tmp_path, old) is None
    assert status["state"] == "failed"
    assert "write failed" in status["reason"]
    assert path.read_bytes() == original


def test_diagnostics_detect_swallowed_rate_limit_and_stop_new_requests(monkeypatch):
    from yfinance.data import YfData
    from yfinance.exceptions import YFRateLimitError
    calls = []
    def blocked(self, url, *args, **kwargs):
        calls.append(url)
        raise YFRateLimitError()
    monkeypatch.setattr(YfData, "get", blocked)
    with ProviderDiagnostics(delay=0) as diagnostic:
        for _ in range(2):
            with pytest.raises(YFRateLimitError):
                YfData.get(None, "https://example.test/data?crumb=secret")
    assert len(calls) == 1
    assert diagnostic.rate_limited
    assert diagnostic.requests == [{"path": "/data", "error_type": "YFRateLimitError"}]
    assert YfData.get is blocked


def test_diagnostics_record_http_failure_without_secrets(monkeypatch):
    from yfinance.data import YfData
    monkeypatch.setattr(YfData, "get", lambda *_: SimpleNamespace(status_code=503))
    with ProviderDiagnostics(delay=0) as diagnostic:
        YfData.get(None, "https://example.test/data?token=secret")
    assert diagnostic.requests == [{"path": "/data", "http_status": 503}]


def test_data_status_distinguishes_missing_current_and_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(recommendations, "DATA_DIR", tmp_path)
    client = app.app.test_client()
    assert client.get("/health").status_code == 200
    assert client.get("/data-status").status_code == 503
    snapshot = publish({"A": report("A")}, ["A"])
    atomic_write(tmp_path / "recommendations.json", snapshot)
    response = client.get("/data-status")
    assert response.status_code == 200
    assert response.json["status"] == "ready"
    assert response.json["complete_count"] == 1
    snapshot["generated_at"] = (utcnow() - timedelta(days=9)).isoformat()
    atomic_write(tmp_path / "recommendations.json", snapshot)
    response = client.get("/data-status")
    assert response.status_code == 503
    assert response.json["status"] == "stale"
    assert client.get("/health").status_code == 200


def test_interrupted_run_resumes_only_remaining_attempts():
    incomplete=report('B')
    incomplete['fcf_margin_3y_pct']=None
    from scoring import evaluate, MODEL_VERSION
    evaluate(incomplete)
    initial={'A':report('A'),'B':incomplete}
    status={'state':'running','started_at':utcnow().isoformat(),'model_version':MODEL_VERSION,
            'universe_count':2,'attempts':{'A':[{'attempt':1}], 'B':[{'attempt':1}]},'stop_reason':None}
    calls=[]
    def fetch(symbol,timeout):
        calls.append(symbol)
        return result(report(symbol))
    reports, finished=collect_reports(['A','B'],fetch,sleep=lambda _:None,
                                     initial_reports=initial,initial_status=status)
    assert calls==['B']
    assert reports['B']['fetch_complete']
    assert finished['attempts']['B'][-1]['attempt']==2
    assert len(finished['attempts']['A'])==1
    assert reports['A']['retrieved_at']==initial['A']['retrieved_at']
    assert finished['resumed_at']
