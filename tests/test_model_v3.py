import copy
from datetime import timedelta
import pandas as pd
from scoring import evaluate, peer_reference, utcnow
from financials import extract_annual
from test_refresh import report


def test_quality_independent_of_missing_pe_targets_and_market_data():
    r=report(); r.update(trailing_pe=None,target_upside_pct=None,market_data_as_of=None)
    evaluate(r)
    assert r['business_quality']==100 and r['opportunity'] is None


def test_analysts_momentum_and_provider_growth_do_not_change_scores():
    r=report(); before=(r['business_quality'],r['opportunity'])
    r.update(target_upside_pct=-99,momentum_pct=-99,earnings_growth_pct=999,revenue_growth_pct=999)
    evaluate(r)
    assert (r['business_quality'],r['opportunity'])==before


def test_smooth_growth_does_not_jump_at_old_boundary():
    r=report();r['eps_cagr_pct']=14.99;evaluate(r);before=r['business_quality']
    r['eps_cagr_pct']=15;evaluate(r)
    assert abs(r['business_quality']-before)<=0.1
    assert r['opportunity']==100


def test_known_losses_are_zero_not_missing():
    r=report();r.update(eps_cagr_pct=None,eps_growth_state='nonpositive_history',earnings_yield_pct=-5)
    evaluate(r)
    assert r['quality_complete'] and r['opportunity_complete']
    assert r['business_quality']==85 and r['opportunity']==65


def test_unknown_growth_is_withheld():
    r=report();r.update(eps_cagr_pct=None,eps_growth_state='missing');evaluate(r)
    assert r['business_quality'] is None and r['opportunity'] is not None


def test_peers_exclude_self_and_require_enough_observations():
    r=report('SELF');pool={f'P{i}':report(f'P{i}') for i in range(8)}
    pool['SELF']=r
    refs=peer_reference(r,pool)
    assert refs['earnings_yield_pct']['count']==8
    assert 'SELF' not in refs['earnings_yield_pct']['symbols']
    del pool['P0']
    assert peer_reference(r,pool)=={}


def test_sector_fallback_is_explicit_and_stale_peers_excluded():
    r=report('SELF');pool={f'P{i}':report(f'P{i}') for i in range(8)}
    for p in pool.values():p['industry']='Different equipment'
    assert peer_reference(r,pool)['fcf_yield_pct']['basis']=='sector'
    pool['P0']['annual_period_end']='2020-01-01'
    assert peer_reference(r,pool)=={}


def test_statement_extraction_matches_periods_and_uses_three_years():
    dates=pd.to_datetime(['2025-12-31','2024-12-31','2023-12-31'])
    income=pd.DataFrame({'Total Revenue':[144,120,100],'Operating Income':[30,24,20],
                         'Net Income':[20,15,10],'Diluted EPS':[2,1.5,1],
                         'EBITDA':[40,34,30]},index=dates).T
    cf=pd.DataFrame({'Free Cash Flow':[18,12,-2]},index=dates).T
    balance=pd.DataFrame({'Total Debt':[40,40,40],'Stockholders Equity':[100,90,80],
                          'Cash And Cash Equivalents':[20,20,20]},index=dates).T
    r=extract_annual(income,cf,balance,200,'USD','USD')
    assert len(r['annual_periods'])==3
    assert round(r['revenue_cagr_pct'])==20
    assert r['fcf_margin_3y_pct']==10
    assert round(r['fcf_positive_years_pct'],2)==66.67
    assert r['earnings_yield_pct']==10
    assert r['fcf_yield_pct']==9
    assert round(r['ebitda_yield_pct'],3)==round(40/220*100,3)
    cf.columns=pd.to_datetime(['2024-12-31','2023-12-31','2022-12-31'])
    missing=extract_annual(income,cf,balance,200,'USD','USD')
    assert missing['annual_period_end']=='2024-12-31' and missing['quality_window_years'] is None


def test_currency_mismatch_only_withholds_valuation_metrics():
    empty=pd.DataFrame()
    r=extract_annual(empty,empty,empty,100,'USD','EUR')
    assert not r['currency_compatible']
    assert r['earnings_yield_pct'] is None
