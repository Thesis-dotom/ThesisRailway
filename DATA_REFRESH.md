# Weekly research refresh

The workflow `.github/workflows/weekly-refresh.yml` requests a run on Sunday at 23:17 UTC and supports **Run workflow** manually. Configure GitHub permissions and Railway autodeploy using `RAILWAY_MIGRATION.md`.

Pipeline: test → collect the configured universe → compute dated peer references → score → validate coverage → write history and current snapshot atomically → commit/push → Railway deployment.

- Universe: 109 manually selected U.S.-listed companies. WNS was removed after its delisting. See `universe_notes.json`.
- At least 80% must return reports and at least 60% must have both complete scores. For 109 names this means 88 reports and 66 complete pairs.
- Missing inputs stay unscored. Known negative earnings follow explicit zero-point rules. A usable independent score remains visible.
- Data calls are paced at 0.5 seconds between GETs and two seconds between companies. Incomplete inputs retry once after a 30-second pause. Missing peer comparisons alone do not trigger redundant downloads.
- A per-company subprocess times out after 60 seconds. Collection has a 90-minute budget and the workflow has a 110-minute timeout.
- Observed provider rate limits stop the run. Failed data validation or writing preserves the prior published snapshot. A failed git push or Railway deployment means the live website still has its old data.
- `.refresh-work` contains checkpoints for diagnosis and explicit recovery. `python refresh_recommendations.py --resume` can continue an interrupted run only when the model and universe match, all saved inputs are less than six hours old, and no rate-limit or other stop reason was recorded. It preserves original retrieval dates and the two-attempt limit. This is not automatic across separate GitHub runners. Saved checkpoints are not served as a successful snapshot. Diagnostic artifacts are retained for 14 days in GitHub.
- `/data-status` returns the snapshot identity, counts, model version and freshness. It returns 503 if missing or over eight days old. `/health` checks process health separately.
- Filters and report links retain snapshot IDs. Earlier model 2 snapshots are explicitly labeled historical and not comparable.

A successful fetch is only one stage. Verify the final GitHub commit, Railway deployment and live `/data-status` identity. Monitor failed runs; scheduled execution and provider availability cannot be guaranteed.

`validate_model.py` records a current-data model comparison and factor-weight sensitivity. It is not a performance backtest. `export_preview.py` regenerates the offline preview when preparing a new distributable package; the deployed Flask site does not depend on that static preview.
