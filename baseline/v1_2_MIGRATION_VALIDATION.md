# Thesis v1.2.1 validation — October 28, 2026

## Outcome

The paced refresh completed successfully at 2026-10-28T17:58:45Z.
Snapshot: 20261028T175845-8140, model 2.0.

| Check | Earlier four-worker run | New paced run |
| --- | ---: | ---: |
| Configured companies | 50 | 50 |
| Reports returned | 45 | 50 |
| Complete records | 15 | 44 |
| Publication | Withheld | Passed |
| Qualifying candidates | Not published | 2 |

The package includes the new current snapshot and its matching historical file.
No thresholds were lowered, missing values filled, or companies removed to pass
the gates. scoring.py, universe.json, templates and styles remain unchanged.
The first-pass result was already 44 complete; six incomplete companies received
one retry and remained excluded. No rate-limit response was observed during this
successful run. The earlier run did not retain diagnostics, so its exact failure
cause cannot be established from the before/after comparison alone.

FLR, NEOG, AZTA, BRKR and COHU lacked trailing P/E. WNS lacked many inputs and
returned HTTP 404 on quote/history requests. WNS ceased NYSE trading after its
October 17, 2025 acquisition; it is a known outdated entry in the original
universe and remains excluded by the data checks. The original 50-company
universe was retained for this comparison. Review ticker changes during normal
universe maintenance rather than treating every missing record as a network bug.
Primary source: https://www.sec.gov/Archives/edgar/data/1356570/000207709625000155/ea026147301ex99-1_wns.htm

Sanitized per-company diagnostics are included in
validation/refresh-status-2026-10-28.json.

## Verified

- 23 automated tests passed under Python 3.12.14 and requirements.lock.
- Tests cover selective retry, incomplete attempts remaining incomplete,
  rate-limit stop, unchanged previous snapshots on coverage/write failure,
  atomic current/history publication, diagnostic redaction and data freshness.
- /data-status returned HTTP 200, status ready, version 1.2.1, and matching
  50 returned / 44 complete / 2 qualifying counts.
- Flask route checks passed for the homepage, educational pages, health, data
  status, Top Opportunities, filters and both saved recommendation reports.
- Candidate-card scores matched the reports from the same snapshot ID.
- PREVIEW.html was refreshed from nine rendered Flask pages using the saved
  snapshot. Its export did not require live provider requests.
- Browser QA verified the 44/50 update stamp, both listed candidates, layout,
  and navigation to a saved company report with matching scores.
- Workflow YAML parsed successfully. It now installs pinned runtime versions,
  saves diagnostics and gives a run summary before committing validated data.
- Existing Gunicorn configuration and port handling passed the prior migration
  HTTP smoke test. The hosting configuration was unchanged in this patch.

## Provenance and limits

The starting source is the October 19 v1.2 archive. v1.2.1 adds the refresh
reliability changes, data-status endpoint, instructions and regenerated preview.
The connected Thesis-dotom/Thesis main branch inspected during this work still
contained v1.0, so it was not used to replace the newer saved source.

No Railway deployment, repository push, subscription purchase, domain change,
or GitHub workflow run was performed in the user's account. Docker is not
available here, so the container image was not built locally. The first run on
the actual GitHub runner and its resulting Railway deployment still need to be
verified using DATA_REFRESH.md. Local success does not establish future provider
availability or confirm that the weekly schedule is active.

PREVIEW.html is an offline snapshot, not a running backend. Saved page/report
links work; live search and filtering need the deployed app. Its contents do not
refresh automatically. The actual app marks snapshots historical after eight
days and /data-status then returns HTTP 503.

Application and data-completeness checks do not validate the investment model's
predictive performance. The model has not been backtested by this work.
