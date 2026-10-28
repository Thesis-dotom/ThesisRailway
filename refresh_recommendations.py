"""Run manually or from the weekly GitHub Actions workflow."""
import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from recommendations import DATA_DIR, load_snapshot
from scoring import MODEL_VERSION, evaluate, age_days

UNIVERSE = Path(__file__).parent / "universe.json"

def publish(reports, universe, previous=None, now=None):
    if len(reports) < len(universe) * 0.8:
        raise ValueError("Fewer than 80% of companies returned data; keeping prior snapshot.")
    usable = [r for r in reports.values() if r["eligible_data"]]
    if len(usable) < len(universe) * 0.6:
        raise ValueError("Fewer than 60% of companies have both complete scores; keeping prior snapshot.")
    previous = previous if previous and previous.get('model_version') == MODEL_VERSION else None
    old = {r['symbol']: r for r in (previous or {}).get('rankings', [])}
    candidates = [r for r in reports.values() if r.get('quality_complete') or r.get('opportunity_complete')]
    candidates.sort(key=lambda r: (r['decision']['combined'] is None,
                                   -(r['decision']['combined'] or 0),
                                   -(r['business_quality'] or 0), r['symbol']))
    rankings = []
    for rank, r in enumerate(candidates, 1):
        before = old.get(r['symbol'])
        changes = []
        if before:
            prior = previous['reports'][r['symbol']]
            old_factors = {e['factor']: e for e in prior['score_evidence']}
            for e in r['score_evidence']:
                was = old_factors.get(e['factor'], {}).get('score')
                if was != e['score']:
                    changes.append(f"{e['factor']}: {was} → {e['score']} points")
        rankings.append({'symbol':r['symbol'], 'name':r['name'], 'rank':rank,
                         'quality':r['business_quality'], 'opportunity':r['opportunity'],
                         'combined':r['decision']['combined'], 'sector':r['sector'],
                         'industry':r['industry'], 'market_cap':r['market_cap'],
                         'category':r['category'], 'screen_match':r['screen_match'],
                         'partial':not r['eligible_data'],
                         'why':' '.join(r['why_like'][:2]), 'risk':r['risks'][0],
                         'change':'New in this model' if before is None else f"Rank change: {before['rank'] - rank:+d}",
                         'reasons':changes or ['First model 3.0 snapshot.' if before is None else 'No factor-score changes.']})
    selected = [r for r in rankings if r['screen_match']]
    removed = []
    for item in (previous or {}).get('recommendations', []):
        if item['symbol'] not in {r['symbol'] for r in selected}:
            removed.append({'symbol':item['symbol'], 'reason':'No longer meets the screen; check All companies and the data notes.'})
    now = now or datetime.now(timezone.utc)
    return {'id':now.strftime('%Y%m%dT%H%M%S')+'-'+now.strftime('%f')[:4],
            'model_version':MODEL_VERSION, 'generated_at':now.isoformat(),
            'universe_count':len(universe), 'universe':universe,
            'fetched_count':len(reports), 'complete_count':len(usable),
            'quality_count':sum(r.get('quality_complete',False) for r in reports.values()),
            'opportunity_count':sum(r.get('opportunity_complete',False) for r in reports.values()),
            'rankings':rankings, 'recommendations':selected, 'reports':reports, 'removed':removed}

def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def worker(symbol, request_delay):
    from app import build_report
    from provider_diagnostics import ProviderDiagnostics
    result = {"report": None, "error_type": None}
    with ProviderDiagnostics(request_delay) as provider:
        try:
            result["report"] = build_report(symbol)
        except Exception as exc:
            result["error_type"] = type(exc).__name__
    result.update(requests=provider.requests, rate_limited=provider.rate_limited)
    return result


def fetch_company(symbol, timeout, output, request_delay):
    try:
        output.unlink(missing_ok=True)
        subprocess.run([sys.executable, __file__, "--worker", symbol,
                        "--output", str(output), "--request-delay", str(request_delay)],
                       check=True, timeout=timeout, capture_output=True)
        result = json.loads(output.read_text())
        r = result.get("report")
        if r is not None and r["symbol"].upper() != symbol:
            raise ValueError("Resolved symbol differs from universe symbol")
        return result
    except (subprocess.SubprocessError, ValueError, OSError, KeyError) as exc:
        return {"report": None, "error_type": type(exc).__name__,
                "requests": [], "rate_limited": False}


def collect_reports(universe, fetcher, *, attempts=2, delay=2, retry_delay=30,
                    max_seconds=5400, sleep=time.sleep, checkpoint=None,
                    initial_reports=None, initial_status=None):
    """Retry only incomplete companies; never merge fields across attempts."""
    reports = copy.deepcopy(initial_reports or {})
    status = copy.deepcopy(initial_status) if initial_status else {"state": "running", "started_at": datetime.now(timezone.utc).isoformat(),
              "model_version": MODEL_VERSION, "universe_count": len(universe),
              "attempts": {}, "stop_reason": None}
    status['universe'] = list(universe)
    if initial_status:
        status['resumed_at'] = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic() + max_seconds
    for attempt in range(1, attempts + 1):
        pending = [symbol for symbol in universe
                   if len(status['attempts'].get(symbol, [])) < attempt
                   and (symbol not in reports or (not reports[symbol].get('fetch_complete')
                        and reports[symbol]['decision']['answer'] != 'Not supported'))]
        if not pending:
            continue
        if attempt > 1:
            sleep(min(retry_delay, max(0, deadline - time.monotonic())))
        retry = []
        for symbol in pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status["stop_reason"] = "Refresh time budget exceeded."
                break
            result = fetcher(symbol, min(60, remaining))
            r = result.get("report")
            if r is not None:
                r = evaluate(r)  # Recheck freshness at collection time.
                reports[symbol] = r
            detail = {"attempt": attempt, "at": datetime.now(timezone.utc).isoformat(),
                      "complete": bool(r and r["fetch_complete"]),
                      "missing_data": r["missing_data"] if r else [],
                      "error_type": result.get("error_type"),
                      "rate_limited": result.get("rate_limited", False),
                      "requests": result.get("requests", [])}
            status["attempts"].setdefault(symbol, []).append(detail)
            description = ("unavailable" if r is None else "annual inputs ready" if r["fetch_complete"]
                           else "withheld: " + ", ".join(r["missing_data"]))
            print(f"{symbol} (attempt {attempt}): {description}", flush=True)
            if detail["rate_limited"]:
                status["stop_reason"] = "Provider rate limit detected; stopped further requests. Retry later."
            status.update(fetched_count=len(reports),
                          raw_complete_count=sum(r["fetch_complete"] for r in reports.values()))
            if checkpoint:
                checkpoint(reports, status)
            if status["stop_reason"]:
                break
            if not r or (not r["fetch_complete"] and r["decision"]["answer"] != "Not supported"):
                retry.append(symbol)
            sleep(min(delay, max(0, deadline - time.monotonic())))
        if status["stop_reason"]:
            break
    return reports, status


def finish_refresh(reports, universe, status, data_dir, previous=None):
    """Commit a complete snapshot only after all collection checks pass."""
    try:
        if status.get("stop_reason"):
            raise ValueError(status["stop_reason"])
        reports = {symbol: evaluate(r, peers=reports) for symbol, r in reports.items()}
        snapshot = publish(reports, universe, previous)
    except ValueError as exc:
        status.update(state="failed", reason=str(exc))
        return None
    try:
        atomic_write(data_dir / "history" / (snapshot["id"] + ".json"), snapshot)
        atomic_write(data_dir / "recommendations.json", snapshot)
    except OSError as exc:
        status.update(state="failed", reason=f"Snapshot write failed: {type(exc).__name__}.")
        return None
    status.update(state="published", snapshot_id=snapshot["id"],
                  fetched_count=snapshot["fetched_count"], complete_count=snapshot["complete_count"],
                  recommendation_count=len(snapshot["recommendations"]))
    return snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--output")
    parser.add_argument("--work-dir", type=Path, default=Path(".refresh-work"))
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted, same-model checkpoint less than six hours old")
    parser.add_argument("--attempts", type=int, choices=(1, 2), default=2)
    parser.add_argument("--delay", type=float, default=2)
    parser.add_argument("--retry-delay", type=float, default=30)
    parser.add_argument("--request-delay", type=float, default=0.5)
    args = parser.parse_args()
    if min(args.delay, args.retry_delay, args.request_delay) < 0:
        parser.error("Delays must be non-negative.")
    if args.worker:
        if not args.output:
            parser.error("--worker requires --output")
        atomic_write(Path(args.output), worker(args.worker, args.request_delay))
        return 0
    universe = json.loads(UNIVERSE.read_text())
    if not universe or len(universe) != len(set(universe)):
        raise ValueError("Universe must be non-empty and contain unique tickers.")
    initial_reports, initial_status = None, None
    if args.resume:
        initial_status = json.loads((args.work_dir / 'refresh-status.json').read_text())
        initial_reports = json.loads((args.work_dir / 'reports.json').read_text())
        recorded_universe = initial_status.get('universe', list(initial_status.get('attempts', {})))
        if (initial_status.get('state') != 'running' or initial_status.get('stop_reason')
                or initial_status.get('model_version') != MODEL_VERSION
                or recorded_universe != universe
                or not 0 <= age_days(initial_status.get('started_at')) <= .25
                or any(not 0 <= age_days(r.get('retrieved_at')) <= .25 for r in initial_reports.values())):
            raise ValueError('Checkpoint is not a recent interrupted run of this model and universe. Start a fresh refresh instead.')
    def checkpoint(reports, status):
        atomic_write(args.work_dir / "reports.json", reports)
        atomic_write(args.work_dir / "refresh-status.json", status)

    with tempfile.TemporaryDirectory() as tmp:
        def fetcher(symbol, timeout):
            return fetch_company(symbol, timeout, Path(tmp) / "company.json", args.request_delay)
        reports, status = collect_reports(universe, fetcher, attempts=args.attempts,
                                          delay=args.delay, retry_delay=args.retry_delay,
                                          checkpoint=checkpoint, initial_reports=initial_reports,
                                          initial_status=initial_status)
    try:
        snapshot = finish_refresh(reports, universe, status, DATA_DIR, load_snapshot())
    finally:
        status["finished_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint(reports, status)
    print(f"Coverage: {len(reports)}/{len(universe)} reports; "
          f"{sum(r['eligible_data'] for r in reports.values())}/{len(universe)} complete.", flush=True)
    if snapshot is None:
        print(f"Refresh failed: {status['reason']} Diagnostics: {args.work_dir / 'refresh-status.json'}", flush=True)
        return 1
    print(f"Published {len(snapshot['recommendations'])} qualifying companies from {len(universe)} screened.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
