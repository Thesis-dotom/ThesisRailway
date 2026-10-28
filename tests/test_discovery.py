import copy
import app
import recommendations as rec
from refresh_recommendations import publish
from scoring import evaluate
from test_refresh import report, save


def test_lower_and_partial_scores_remain_discoverable(tmp_path,monkeypatch):
    monkeypatch.setattr(rec,'DATA_DIR',tmp_path)
    reports={s:report(s) for s in ['AAA','BBB','CCC','DDD','EEE']}
    reports['BBB']['earnings_yield_pct']=1
    reports['BBB']['fcf_yield_pct']=1
    reports['BBB']['ebitda_yield_pct']=1
    evaluate(reports['BBB'])
    reports['CCC']['earnings_yield_pct']=None
    evaluate(reports['CCC'])
    reports['DDD']['fcf_margin_3y_pct']=None
    evaluate(reports['DDD'])
    snapshot=publish(reports,list(reports))
    save(tmp_path,snapshot)
    assert rec.page_data(snapshot)['total']==5
    assert rec.page_data(snapshot,view='screen')['total']==2
    assert rec.page_data(snapshot,view='watchlist')['total']==2
    assert rec.page_data(snapshot,view='partial')['total']==2
    assert rec.page_data(snapshot,minimum_quality=80)['total']==4
    client=app.app.test_client()
    page=client.get('/discover?minimum_quality=80&sort=quality')
    assert page.status_code==200 and b'4 research candidates' in page.data
    assert b'CCC' in page.data and b'DDD' not in page.data
    assert client.get('/discover?minimum_quality=45').status_code==400
    assert client.get('/discover?sort=nonsense').status_code==400
    assert client.get('/discover?size=nonsense').status_code==400
    assert b'No companies match' in client.get('/discover?sector=NoSuchSector').data


def test_sources_keep_snapshot_identity(tmp_path,monkeypatch):
    monkeypatch.setattr(rec,'DATA_DIR',tmp_path)
    snapshot=publish({'AAA':report('AAA')},['AAA'])
    save(tmp_path,snapshot)
    monkeypatch.setattr(app,'get_cached_report',lambda _: (_ for _ in ()).throw(AssertionError('Must use saved snapshot')))
    client=app.app.test_client()
    response=client.get('/sources/AAA?snapshot='+snapshot['id'])
    assert response.status_code==200
    assert snapshot['id'].encode() in response.data
    assert client.get('/sources/MISSING?snapshot='+snapshot['id']).status_code==410
