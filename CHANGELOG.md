# v1.3 form simplification — October 28, 2026

- Require only the company name for visitor suggestions.
- Replace the mandatory explanation with a collapsed optional note, without a minimum length.
- Replace the acknowledgement checkbox with a short informational note.
- Update the private inbox, preview and upload guide for name-only submissions.

# v1.3 — October 28, 2026

- Replace the core heuristic with dated annual metrics, smooth scoring, richer cash-flow measures and disclosed industry/sector comparisons.
- Score Quality and Opportunity independently; distinguish missing values from known losses.
- Remove analyst targets and momentum from core scores; count earnings growth once.
- Expand the sample to 109 companies and remove the delisted WNS entry. Keep all usable companies visible through ranking, watchlist, partial and unrated views.
- Add research-preference matching and a private, persisted company-suggestion inbox.
- Add PostgreSQL support, CSRF protection, owner authentication, rate limits and escaped submissions.
- Extend the weekly scan budget, add guarded recovery of recent interrupted runs, preserve strict publication gates and add PostgreSQL integration tests in the workflow.
- Include an offline preview with working saved-data filters, complete Railway instructions and a current-model sensitivity comparison.
- No performance backtest or external deployment is claimed. See VALIDATION.md for measured results.

# v1.2.1 refresh reliability — October 28, 2026

- Replace four concurrent fetch workers with one paced worker at a time.
- Retry incomplete or failed companies once; never refetch complete companies
  within the run or combine fields from different attempts.
- Save per-company diagnostics and checkpoints; stop on an observed rate limit.
- Preserve the 80% retrieval and 60% completeness gates and prior good snapshot.
- Add /data-status for deployed snapshot freshness and coverage verification.
- Use pinned runtime dependencies in Actions and retain diagnostics artifacts.
- Add nine regression tests for recovery, safe failure, diagnostics and status.

# v1.2 review and verification (historical)

## Audit fixes
- Old top-ten scores were constants. Category breakdowns were proportionally
  allocated from totals. Both mechanisms were removed.
- Missing data now suppresses aggregate scores and screening verdicts.
- Ranking is consistent: combined descending, Quality descending, ticker.
- Report copy uses supplied company descriptions and actual numeric inputs.
- Unknown description/sector/data remains explicitly unavailable.
- Source pages distinguish the provider from links for independent verification.
- Search results no longer repeat large promotional cards before the report.
- All quality/opportunity rubric displays now match the new scoring module.

## New behavior
- Four bounded workers scan 50 configured companies; each request process has
  a 60-second timeout. Failed coverage gates prevent publication.
- Weekly GitHub workflow: Sunday 23:17 UTC plus manual trigger.
- Atomic JSON publication; persistent repository snapshots.
- Ten results per page, sector and size filters, no threshold relaxation.
- Stable pagination and company-report links use snapshot IDs.
- New entries, removals, rank movements, score movements and factor changes.
- Eight-day stale warning; old reports no longer give a current screening verdict.

## Verification
14 automated tests passed before packaging: routing, name resolution, missing
inputs, unsupported sectors, stale data, negative P/E, sort order, nonduplicate
pagination, filters, matching list/report scores, invalid request handling,
publication failure preservation, zero qualifiers, removals, historical versions,
elimination of editorial overrides, and component-change reasons.
Python compilation and structure checks also passed.
Live market fetch and first full-refresh outcome are recorded in VALIDATION.md.

## Limits
This is a quantitative screening model, not full investment research or a
backtested stock picker. Company-specific catalysts and competitive position
require separate review. The original 150/60 screening thresholds are retained
but not recalibrated. See README and Methodology for operational/data limits.
