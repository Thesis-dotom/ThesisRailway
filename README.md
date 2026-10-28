# Thesis 1.3

A Flask company-research website with independent Quality and Opportunity scores, transparent annual evidence, a weekly saved research universe, a preference-based company finder, and private company suggestions.

**Start here:** open `PREVIEW.html` to inspect the saved-data preview. Follow `RAILWAY_MIGRATION.md` for the full upload walkthrough. The website itself is the whole source folder, not the preview file.

## What changed

- Model 3.0 uses aligned annual financials and smooth scores. Earnings growth appears once; analyst targets and momentum are context only.
- Dated industry/sector references require at least eight other comparable observations, with the group and tickers shown.
- The 109-company sample exposes all usable reports, strict screen matches, a Quality watchlist, partial scores and unrated reasons.
- `/discover` filters research candidates by sector, size, priority and minimum Quality.
- `/suggest-company` saves visitor requests privately. Only a company name is required; the ticker and expandable note are optional. `/admin/login` opens the owner review inbox; PostgreSQL is required in production.
- A weekly GitHub Actions job collects data, checks coverage, retains the last good snapshot on failure, and commits a successful snapshot for Railway autodeploy.

Weights, peer selection and thresholds are provisional. This is research software, not a backtested return forecast. See `/methodology` and `validation/MODEL_COMPARISON.md`.

## Run locally

Requires Python 3.12. In a terminal opened in this folder:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.lock
python app.py
```

Open the local URL printed by Flask (normally `http://127.0.0.1:5000`). Local development stores suggestions in `instance/suggestions.sqlite3`, ignored by git. Set a local `ADMIN_PASSWORD` of at least 16 characters if testing the inbox. Set a persistent random `SECRET_KEY` to keep local sessions across restarts. Production needs the variables in the Railway guide and HTTPS.

## Validate and refresh

```bash
python -m pip install pytest beautifulsoup4
python -m pytest -q
python refresh_recommendations.py
python validate_model.py
python export_preview.py
```

A manual refresh makes external provider requests and may take substantial time. Do not run overlapping scans. `validate_model.py` and `export_preview.py` use saved data; the preview export does not read the private inbox.

For PostgreSQL integration tests, set `DATABASE_TEST_URL` to a **disposable database named `thesis_test`**. The tests reset its tables. Never point that variable at a real inbox. The supplied GitHub Actions workflow creates and tests a temporary PostgreSQL service automatically.

## Files

- `app.py`, `templates/`, `static/`: public website and live report requests.
- `financials.py`, `scoring.py`: dated annual metrics and model 3 rules.
- `recommendations.py`, `refresh_recommendations.py`, `universe.json`: snapshot serving and refresh pipeline.
- `submissions.py`: private persisted inbox, owner access, validation and rate limits.
- `data/recommendations.json`, `data/history/`: public saved research data; never visitor submissions.
- `baseline/`: earlier scoring code and snapshot retained for comparison.
- `validation/`: recorded validation evidence, current model comparison and sensitivity output.
- `PREVIEW.html`: standalone preview; no backend or live form submission.
- `RAILWAY_MIGRATION.md`: complete deployment instructions.
- `Dockerfile`, `gunicorn.conf.py`, `requirements.lock`: production runtime.

No production secrets or visitor submissions are included. This package does not activate hosting, account billing or the GitHub schedule by itself.
