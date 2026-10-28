import copy
import json
from datetime import datetime, timezone, timedelta
import pytest
import app
import recommendations as rec
from refresh_recommendations import publish, atomic_write
from scoring import evaluate, MODEL_VERSION, utcnow

def report(symbol="TEST"):
    r={"symbol":symbol,"name":f"{symbol} Company","sector":"Industrials","industry":"Equipment",
       "price":100,"market_cap":3e9,"trailing_pe":10,"forward_pe":9,"peg":1,"beta":1,
       "target_upside_pct":60,"revenue_growth_pct":30,"earnings_growth_pct":30,
       "profit_margin_pct":30,"roe_pct":30,"debt_to_equity":20,"free_cash_flow":1e8,
       "momentum_pct":30,"currency":"USD","market_data_as_of":utcnow().isoformat(),
       "financial_period_end":utcnow().isoformat(),"cashflow_period_end":utcnow().isoformat(),
       "annual_period_end":utcnow().isoformat(),"quality_window_years":2,
       "currency_compatible":True,"operating_return_pct":25,"operating_margin_3y_pct":20,
       "fcf_margin_3y_pct":10,"fcf_positive_years_pct":100,"net_debt_to_ebitda":0,
       "revenue_cagr_pct":20,"eps_cagr_pct":25,"eps_growth_state":"positive_history",
       "leverage_state":"ratio_available","earnings_yield_pct":10,"fcf_yield_pct":10,
       "ebitda_yield_pct":20,"annual_periods":[],"metric_notes":[],
       "retrieved_at":utcnow().isoformat(),"sources":[],"exchange":"NYSE",
       "change_opinion":[],"data_warning":"Test fixture"}
    r['peer_reference']={k:{'median':v,'count':8,'basis':'sector','group':'Industrials',
                            'as_of':utcnow().isoformat(),'symbols':list('ABCDEFGH'),
                            'oldest_period':'2025-06-30','newest_period':'2025-12-31'}
                         for k,v in {'operating_margin_3y_pct':10,'fcf_margin_3y_pct':5,
                                     'earnings_yield_pct':5,'fcf_yield_pct':5,'ebitda_yield_pct':10}.items()}
    return evaluate(r)

@pytest.fixture
def data_dir(tmp_path,monkeypatch):
    monkeypatch.setattr(rec, "DATA_DIR", tmp_path)
    return tmp_path

def save(data_dir,snapshot):
    atomic_write(data_dir/"recommendations.json",snapshot)
    atomic_write(data_dir/"history"/(snapshot["id"]+".json"),snapshot)

def test_missing_inputs_withhold_aggregate():
    r=report(); r["fcf_margin_3y_pct"]=None
    evaluate(r)
    assert r["business_quality"] is None
    assert r["opportunity"] is not None
    assert not r["eligible_data"]

def test_outdated_and_unsupported_excluded():
    r=report(); r["market_data_as_of"]="2020-01-01"; evaluate(r)
    assert not r["eligible_data"]
    r=report(); r["sector"]="Financial Services"; evaluate(r)
    assert r["decision"]["answer"]=="Not supported"

def test_nonpositive_pe_is_not_cheap():
    r=report(); r["earnings_yield_pct"]=-10; evaluate(r)
    assert r["opportunity_breakdown"][0][1]==0

def test_sort_pagination_filters_and_shared_reports(data_dir):
    reports={f"T{i:02}":report(f"T{i:02}") for i in range(23)}
    snapshot=publish(reports,list(reports))
    save(data_dir,snapshot)
    first=rec.page_data(snapshot,1)
    second=rec.page_data(snapshot,2)
    assert len(first["items"])==10 and len(second["items"])==10
    assert not {x["symbol"] for x in first["items"]}&{x["symbol"] for x in second["items"]}
    assert rec.page_data(snapshot,3)["has_more"] is False
    assert rec.page_data(snapshot,size="small")["total"]==0
    assert first["items"][0]["symbol"]=="T00"
    assert rec.saved_report("T00")["business_quality"]==first["items"][0]["quality"]
    client=app.app.test_client()
    page=client.get("/top-opportunities").get_data(as_text=True)
    assert "Show more companies" in page
    assert client.get(f"/search?q=T00&snapshot={snapshot['id']}").status_code==200
    assert client.get("/top-opportunities?page=abc").status_code==400
    assert client.get("/top-opportunities?snapshot=../../etc/passwd").status_code==400

def test_failed_refresh_preserves_old_snapshot(data_dir):
    old=publish({"A":report("A")},["A"]); save(data_dir,old)
    original=(data_dir/"recommendations.json").read_bytes()
    with pytest.raises(ValueError): publish({},["A"],old)
    assert (data_dir/"recommendations.json").read_bytes()==original
    bad=report("A"); bad["eligible_data"]=False
    with pytest.raises(ValueError): publish({"A":bad},["A"],old)

def test_zero_qualifiers_and_removals(data_dir):
    before=publish({"A":report("A")},["A"])
    r=report("A"); r["opportunity"]=1; r["screen_match"]=False
    after=publish({"A":r},["A"],before)
    assert after["recommendations"]==[]
    assert after["removed"][0]["reason"]=="No longer meets the screen; check All companies and the data notes."

def test_historical_pagination_and_report_stay_together(data_dir):
    old=publish({"A":report("A")},["A"],now=utcnow()-timedelta(days=9))
    save(data_dir,old)
    new=publish({"B":report("B")},["B"])
    save(data_dir,new)
    assert rec.saved_report("A",old["id"])["decision"]["answer"]=="Historical snapshot"
    assert rec.load_snapshot(old["id"])["recommendations"][0]["symbol"]=="A"
    assert rec.load_snapshot()["recommendations"][0]["symbol"]=="B"

def test_no_fixed_editorial_score(monkeypatch):
    from test_app import FakeTicker
    monkeypatch.setattr(app.yf,"Ticker",FakeTicker)
    r=app.build_report("MOD")
    assert r["business_quality"] is None
    assert r["rating_source"].startswith("Quantitative")
    assert "selected" not in r["full_report"]["overview"]

def test_incomplete_report_renders(monkeypatch,data_dir):
    r=report();r["earnings_yield_pct"]=None;evaluate(r)
    monkeypatch.setattr(app,"get_cached_report",lambda _:r)
    response=app.app.test_client().get("/search?q=TEST")
    assert response.status_code==200
    assert b"Available for research" in response.data or b"Quality watchlist" in response.data

def test_component_score_changes_have_reasons():
    old=publish({"A":report("A")},["A"])
    r=report("A"); r["revenue_cagr_pct"]=5; evaluate(r)
    new=publish({"A":r},["A"],old)
    assert any("Annualized revenue growth" in x for x in new["recommendations"][0]["reasons"])
