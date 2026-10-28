"""Read-only serving of dated research snapshots and independently rated companies."""
import copy
import json
import os
from pathlib import Path
from scoring import MODEL_VERSION, age_days

DATA_DIR = Path(os.getenv('THESIS_DATA_DIR', Path(__file__).parent / 'data'))
VIEWS = {'all','screen','watchlist','partial','excluded'}
SORTS = {'combined','quality','opportunity','name'}


def load_snapshot(version=None):
    if version is not None and (len(version) != 20 or not all(c.isalnum() or c == '-' for c in version)):
        raise ValueError('Invalid snapshot identifier')
    path = DATA_DIR / 'recommendations.json' if version is None else DATA_DIR / 'history' / (version + '.json')
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or (version is None and data.get('model_version') != MODEL_VERSION):
        return None
    if data.get('model_version') not in {'2.0',MODEL_VERSION}:
        return None
    return data


def is_stale(snapshot):
    return not -1 <= age_days(snapshot.get('generated_at')) <= 8


def saved_report(query, version=None):
    snapshot = load_snapshot(version)
    if not snapshot:
        return None
    key = query.strip().casefold()
    report = next((r for r in snapshot['reports'].values() if key in (r['symbol'].casefold(),r['name'].casefold())),None)
    if report:
        report = copy.deepcopy(report)
        report['snapshot_id'] = snapshot['id']
        report['legacy_model'] = snapshot['model_version'] != MODEL_VERSION
        if is_stale(snapshot):
            report['decision'] = {'answer':'Historical snapshot','class':'maybe',
                                  'combined':report['decision'].get('combined'),
                                  'reason':'Refresh is overdue. These figures describe the saved data date.'}
        return report


def page_data(snapshot, page=1, sector='', size='', view='all', sort='combined', minimum_quality=0):
    if view not in VIEWS or sort not in SORTS or size not in {'','small','mid','large'}:
        raise ValueError('Invalid filter')
    reports = (snapshot or {}).get('reports',{})
    ranked = (snapshot or {}).get('rankings',(snapshot or {}).get('recommendations',[]))
    if snapshot and snapshot.get('model_version') == '2.0':
        ranked = [dict(r, combined=r.get('combined', (r.get('quality') or 0) + (r.get('opportunity') or 0)),
                       category='screen', screen_match=True, partial=False) for r in ranked]
    excluded = []
    for symbol in (snapshot or {}).get('universe',[]):
        r = reports.get(symbol)
        if r is None or (r.get('business_quality') is None and r.get('opportunity') is None):
            excluded.append({'symbol':symbol,'has_report':r is not None,'name':r['name'] if r else symbol,
                             'sector':r.get('sector','Unknown sector') if r else 'Unknown sector',
                             'market_cap':r.get('market_cap') if r else None,
                             'reason':r['decision']['reason'] if r else 'Data retrieval failed.',
                             'missing':r.get('missing_data',[]) if r else ['Provider data unavailable']})
    counts = {'all':len(ranked), 'screen':sum(r.get('screen_match',True) for r in ranked),
              'watchlist':sum(r.get('category')=='watchlist' for r in ranked),
              'partial':sum(r.get('partial',False) for r in ranked),'excluded':len(excluded)}
    items = excluded if view=='excluded' else list(ranked)
    if view=='screen': items=[r for r in items if r.get('screen_match',True)]
    if view=='watchlist': items=[r for r in items if r.get('category')=='watchlist']
    if view=='partial': items=[r for r in items if r.get('partial',False)]
    def matches_size(r):
        cap = r.get('market_cap')
        return not size or (cap is not None and ((size=='small' and cap<2e9) or (size=='mid' and 2e9<=cap<10e9) or (size=='large' and cap>=10e9)))
    items=[r for r in items if (not sector or r['sector']==sector) and matches_size(r)
           and (minimum_quality<=0 or (r.get('quality') is not None and r['quality']>=minimum_quality))]
    if view!='excluded':
        if sort=='name': items.sort(key=lambda r:r['name'].casefold())
        else: items.sort(key=lambda r:(r.get(sort) is None,-(r.get(sort) or 0),
                                      -(r.get('quality') or 0) if sort=='combined' else 0,r['symbol']))
    return {'items':items[(page-1)*10:page*10], 'has_more':page*10<len(items), 'total':len(items),
            'sectors':sorted({r.get('sector','Unknown sector') for r in reports.values()}),
            'page':page,'snapshot':snapshot,'stale':is_stale(snapshot) if snapshot else False,
            'sector':sector,'size':size,'view':view,'sort':sort,'minimum_quality':minimum_quality,'counts':counts}
