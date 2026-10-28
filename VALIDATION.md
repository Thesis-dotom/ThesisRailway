# Thesis 1.3 validation — 28 October 2026

## Measured result

Current snapshot: `20261028T190809-9403` (2026-10-28T19:08:09.940396+00:00); model 3.0.

| Check | Result |
| --- | --- |
| Configured companies / returned reports | 109 / 109 |
| Both scores complete | 104 |
| Quality complete / Opportunity complete | 104 / 107 |
| At least one usable score | 107 |
| Strict screen matches | 10 |
| Quality watchlist | 19 |
| Partial / unrated | 3 / 2 |
| Automated tests | 43 passed under Python 3.12 |
| Dependency consistency | pip check passed |
| Structure and Python syntax | Passed |
| Workflow YAML | Parsed; 110-minute job timeout |

The paced scan began at 18:31 UTC. The local execution environment stopped the process after its first pass and one retry. A guarded recovery completed the remaining allowed retries from the saved checkpoints and published at 19:08 UTC. No previously complete company was re-fetched, no fields were merged across attempts, and original retrieval times were retained. Publication gates remained at 80% returned and 60% with both scores complete. The original attempt diagnostics and resume timestamp are in `validation/model_3_refresh_status.json`.

AIT, PH and CSCO have Opportunity scores but lack the annualized diluted EPS growth input needed for Quality. ANET and BMI are unrated because operating capital/debt-related inputs are missing. A missing debt value was not assumed to be zero.

## Verified behaviors

- Independent score availability, known losses versus missing inputs, smooth factor changes, annual alignment/currency checks, peer minimums and expiry.
- Selective retry, recent interrupted-run recovery, rate-limit stopping, no merging of partial attempts, coverage/write failure preserving the prior current snapshot, matching history/current files and stale-data signaling.
- Ranking/filter/pagination consistency, lower-scoring and partial companies staying visible, and source links retaining their report snapshot.
- Actual local SQLite persistence across independent web sessions, validation, CSRF protection, form and login rate limits, escaped submitted text, owner access and session expiry, inbox review status, and failed writes never reported as saved.
- Production submission routes refuse to use ephemeral SQLite in place of PostgreSQL.
- `/data-status` returned HTTP 200, `ready`, app 1.3, model 3.0 and the counts above.
- 232 public saved pages exported successfully from the Flask routes. Every saved company report was checked for an actual rendered report, rather than merely an HTTP 200 error page.
- Browser QA checked the updated desktop rankings, page-two ranks, snapshot-preserving report navigation, and a Technology + Quality ≥80 finder query returning six candidates.
- Browser QA checked the suggestion form at a 390-pixel preview width, validation, and the explicit offline notice on submission. The offline preview never claims to save a request.

## Suggestion form simplification

The October 28 form update requires only the company name. A persistence test verifies name-only submissions, the empty-note inbox display, and short optional notes; the 2,000-character note limit remains enforced. No database migration is required. Browser QA confirmed that the note starts collapsed, expands correctly, and name-only submission reaches the offline preview notice without a required explanation or acknowledgement checkbox. All 43 automated tests passed after this change.

## Model comparison

`validation/MODEL_COMPARISON.md` and `model_comparison.csv` compare old/new rules on current data. Nine companies with usable model 3 scores were withheld by model 2 on those same records. Twenty factor-weight perturbations are recorded in `weight_sensitivity.json`. This is a current-data sensitivity analysis, not a historical performance backtest. Weights and screen thresholds remain provisional.

## Deployment limits

No Railway service, subscription, repository push, domain change, account automation or production database was created in the user's account. The GitHub schedule is packaged, not activated. Follow `RAILWAY_MIGRATION.md`, including a manual workflow run and a real submission/redeploy persistence check.

Docker and a PostgreSQL server were not available locally. The container was not built here, and local inbox tests used SQLite. The supplied GitHub workflow provisions a disposable PostgreSQL 17 service and runs the same persistence/security tests against it as well; that actual GitHub run still needs to pass. Do not treat the local tests as a completed Railway deployment test.

Provider availability and future successful refreshes cannot be guaranteed. A stale or failed refresh keeps the last good data visible with date/status signals. The static `PREVIEW.html` has no live provider connection or submission backend; its filters use the bundled snapshot.

Earlier validation notes are preserved under baseline/ and describe older versions only.
