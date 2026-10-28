"""Current-snapshot comparison and weight sensitivity; never a return backtest."""
import copy
import csv
import importlib.util
import json
from pathlib import Path
import pandas as pd
from recommendations import load_snapshot


def main():
    root=Path(__file__).parent
    snapshot=load_snapshot()
    if not snapshot: raise RuntimeError('Current model snapshot required')
    spec=importlib.util.spec_from_file_location('baseline_v2',root/'baseline/scoring_v2.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rows=[]
    for symbol,r in snapshot['reports'].items():
        earlier=old.evaluate(copy.deepcopy(r))
        rows.append({'symbol':symbol,'name':r['name'],'old_quality':earlier['business_quality'],
                     'old_opportunity':earlier['opportunity'],'old_combined':earlier['decision']['combined'],
                     'new_quality':r['business_quality'],'new_opportunity':r['opportunity'],
                     'new_combined':r['decision']['combined'],'new_category':r['category'],
                     'old_missing':'; '.join(earlier['missing_data']),
                     'new_missing':'; '.join(r['missing_data'])})
    full=[r for r in snapshot['reports'].values() if r['eligible_data']]
    baseline=sorted(full,key=lambda r:(-r['decision']['combined'],-r['business_quality'],r['symbol']))
    base_rank={r['symbol']:i+1 for i,r in enumerate(baseline)}
    scenarios=[]
    for factor in baseline[0]['score_evidence']:
        for multiplier in (.8,1.2):
            changed=[]
            for r in full:
                scores={}
                for group in ('quality','opportunity'):
                    items=[e for e in r['score_evidence'] if e['group']==group]
                    denom=sum(e['maximum']*(multiplier if e['key']==factor['key'] else 1) for e in items)
                    scores[group]=sum(e['score']*(multiplier if e['key']==factor['key'] else 1) for e in items)/denom*100
                changed.append({'symbol':r['symbol'],'quality':round(scores['quality'],1),
                                'combined':round(round(scores['quality'],1)+round(scores['opportunity'],1),1)})
            changed.sort(key=lambda r:(-r['combined'],-r['quality'],r['symbol']))
            ranks={r['symbol']:i+1 for i,r in enumerate(changed)}
            baseline_screen={r['symbol'] for r in baseline if r['screen_match']}
            screen={r['symbol'] for r in changed if r['quality']>=60 and r['combined']>=150}
            scenarios.append({'factor':factor['factor'],'multiplier':multiplier,
                              'top10_overlap':len({r['symbol'] for r in baseline[:10]} & {r['symbol'] for r in changed[:10]}),
                              'largest_rank_move':max(abs(base_rank[s]-ranks[s]) for s in ranks),
                              'screen_entries':sorted(screen-baseline_screen),'screen_exits':sorted(baseline_screen-screen)})
    valid=[r for r in rows if r['old_combined'] is not None and r['new_combined'] is not None]
    correlation=float(pd.Series([r['old_combined'] for r in valid]).rank().corr(pd.Series([r['new_combined'] for r in valid]).rank())) if len(valid)>2 else None
    restored=[r['symbol'] for r in rows if r['old_combined'] is None and (r['new_quality'] is not None or r['new_opportunity'] is not None)]
    folder=root/'validation';folder.mkdir(exist_ok=True)
    with (folder/'model_comparison.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (folder/'weight_sensitivity.json').write_text(json.dumps({'snapshot_id':snapshot['id'],'scenarios':scenarios},indent=2))
    text=['# Current-snapshot model check','',f"Snapshot: {snapshot['id']} ({snapshot['generated_at']}).",'',
          'This is a comparison of scoring rules on the current dataset, plus a small weight-sensitivity exercise. It is not a historical performance test, an optimized portfolio or evidence that one model earns better returns.','',
          f"- Universe: {snapshot['universe_count']}; reports returned: {len(rows)}.",
          f"- Model 3 complete pairs: {len(full)}; companies with at least one score: {len(snapshot['rankings'])}.",
          f"- Model 2 complete pairs when applied to these same current reports: {sum(r['old_combined'] is not None for r in rows)}.",
          f"- Newly visible usable companies previously withheld by model 2: {', '.join(restored) or 'None'}.",
          f"- Rank correlation among the {len(valid)} companies with both models complete: {correlation:.3f}." if correlation is not None else '- Too few shared complete reports for rank correlation.',
          '', 'Model 2 uses its original provider ratios, growth inputs, analyst targets and momentum. Model 3 uses aligned annual data and peer medians. Both are evaluated on the raw fields collected in this refresh; the definitions intentionally differ. This comparison isolates the current scoring rules, not historical investment returns.',
          '', '## Factor sensitivity', '',
          'Each factor weight is independently increased or decreased by 20%, then that score group is normalized back to 100. Other factors are held fixed. The screen thresholds remain unchanged. Rank movement is measured only within companies with both complete scores.','',
          '| Factor | Weight multiplier | Top 10 retained | Largest rank move | Screen entries / exits |',
          '| --- | --- | --- | --- | --- |']
    for s in scenarios:
        text.append(f"| {s['factor']} | {s['multiplier']} | {s['top10_overlap']}/10 | {s['largest_rank_move']} | {', '.join(s['screen_entries']) or 'None'} / {', '.join(s['screen_exits']) or 'None'} |")
    text += ['', '## Before claiming investment performance','',
             'Keep dated weekly snapshots and model versions for forward observation. For a valid historical study, obtain point-in-time filings and prices, include delisted securities and a contemporaneous universe, set a fixed rebalance rule and transaction costs, select an appropriate benchmark, and reserve an untouched out-of-sample period. Do not fill old periods with today’s revised fundamentals. No historical dataset meeting those conditions is included here.']
    (folder/'MODEL_COMPARISON.md').write_text('\n'.join(text)+'\n')
    print(json.dumps({'snapshot':snapshot['id'],'complete_pairs':len(full),'rated':len(snapshot['rankings']),
                      'restored':restored,'shared_model_correlation':correlation,'scenarios':len(scenarios)}))

if __name__=='__main__': main()
