# Upload Thesis 1.3 to Railway

Prepared 28 October 2026. This guide is for the complete Flask application in this folder. The package has not been deployed to your Railway account. Your existing website remains available while you set up and check the new one.

## 1. Open the package and preview

1. Download the ZIP and extract it. Open the extracted `thesis-v1-3` folder.
2. Double-click `PREVIEW.html`. It opens the updated design, saved company reports, ranking views and company finder in your browser. Use **Mobile view** to inspect a narrow layout.
3. The preview uses the bundled snapshot. It does not refresh data, save suggestions or sign you in. Those functions run in the deployed application.
4. At the folder's top level, confirm you see `app.py`, `Dockerfile`, `requirements.lock`, `templates`, `static`, `data`, and `.github`.
5. The website upload is this whole application's source, not just `PREVIEW.html` and not the ZIP itself.

## 2. Put this version in a new private GitHub repository

Using a new repository called `ThesisRailway` keeps the existing deployment easy to restore and prevents an old service from deploying these changes unexpectedly.

The least error-prone route is [GitHub Desktop](https://desktop.github.com/):

1. Install GitHub Desktop and sign in to your GitHub account.
2. Choose **File → New repository**. Name it `ThesisRailway`. Choose a local parent folder outside the extracted package. Leave the Git ignore and license choices at their defaults; the package supplies its own ignore rules.
3. Click **Create repository**, then **Repository → Show in Explorer** on Windows or **Show in Finder** on Mac.
4. Copy **the contents** of the extracted `thesis-v1-3` folder into that repository folder. Do not copy the outer folder as an extra directory layer.
5. Include `.github`, `.gitignore`, and `.dockerignore`. On Mac, press **Command–Shift–.** to reveal dot-prefixed files if needed. Do not copy a local virtual environment, `.refresh-work`, `.env`, or an `instance` database. These are not included in the delivered package.
6. In GitHub Desktop, review the changed files. In the summary box enter `Upload Thesis 1.3` and click **Commit to main**.
7. Click **Publish repository**, keep **Keep this code private** checked, and publish.
8. Open the repository on GitHub. At its top level you should see `app.py` and `Dockerfile`. Open `.github/workflows/weekly-refresh.yml` and confirm the file exists. The refresh cannot run if that folder was missed.
9. Confirm the default branch is `main` under repository settings. The weekly schedule runs on the default branch.

If you prefer your existing repository, back it up first, then replace its application files deliberately. Check which existing services deploy from that branch before pushing. The instructions below assume the new repository.

## 3. Connect Railway to the repository

1. Open [Railway](https://railway.com/) and sign in with GitHub.
2. Choose a paid plan if required. As checked on the preparation date, Hobby has a **$5/month minimum including $5 of resource usage**, and usage above that is extra. The web service and PostgreSQL database both consume resources. This is not a fixed $5 total bill. Check current pricing and usage alerts in Railway before deploying.
3. Click **New Project → Deploy from GitHub repo**.
4. Authorize Railway's GitHub integration to access `ThesisRailway` and select that repository. If it is absent, edit the integration's repository access and refresh the list.
5. Select `main` as the deployment branch. Name the web service `Thesis` if you want a clear label.
6. Railway should detect the included `Dockerfile`. Its command already starts Gunicorn correctly. Leave custom build and start commands blank. If a manual start command is needed, use exactly `gunicorn --config gunicorn.conf.py app:app`.

7. Leave **Root Directory** blank/default, because `app.py` is at the repository root. If you uploaded an extra folder layer, fix the repository layout before continuing.
8. The first build may begin immediately. The research pages can start before the private suggestion storage is configured; suggestions remain unavailable until the next steps are finished.

## 4. Add persistent storage for suggestions

1. In the same Railway project, click **+ New → Database → PostgreSQL**.
2. Wait for the database service to become ready. Keep its database volume attached.
3. Open the **Thesis web service**, then **Variables**.
4. Add a **reference variable** named `DATABASE_URL` pointing to the PostgreSQL service's `DATABASE_URL`. Use Railway's variable-reference picker where available.
5. If the database service is named `Postgres`, the value is `${{Postgres.DATABASE_URL}}`. If its service name is different, choose that actual service in the picker. Do not put this reference into a Python file. It belongs in the web service's Railway Variables tab.
6. Keep PostgreSQL private. The app connects through Railway's internal connection; it does not need a public database URL.
7. Suggestions are stored in PostgreSQL, so redeploying the web service does not erase the inbox. The local SQLite option is for development only and is deliberately disabled in production without a database connection.
8. Enable an appropriate database backup schedule in Railway's database/volume backup controls. A persistent volume is not a backup. Review the displayed retention and storage cost. Database backups protect submissions; GitHub stores the public research snapshots separately.

The application creates its two small database tables on the first database-backed request. No separate migration command or manual SQL is required for this release.

## 5. Add the web service's remaining variables

Add these to **Thesis → Variables**, not the database's Variables tab:

| Variable | Value |
| --- | --- |
| `THESIS_ENV` | `production` |
| `PORT` | `8080` |
| `WEB_CONCURRENCY` | `1` |
| `DATABASE_URL` | The reference configured above |
| `SECRET_KEY` | A newly generated random secret, at least 32 characters; use 64 random characters if convenient |
| `ADMIN_PASSWORD` | A unique owner password of at least 16 characters; store it in your password manager |

Use a password manager's random generator for the two secrets. Keep them different. Do not upload them to GitHub, paste them into the README, or reuse a password from another account. There are no prefilled production credentials in this package.

`SECRET_KEY` protects the session cookie and form tokens. `ADMIN_PASSWORD` opens the private owner inbox. If either required secret is too short, the corresponding protected functions remain unavailable. Rotating the owner password or session secret invalidates existing owner sessions.

Do not enable `FLASK_DEBUG`. No financial API key is needed for the present Yahoo/yfinance integration. GitHub's public-data refresh does not need the database URL or the owner secrets.

## 6. Configure and deploy the web service

1. In **Thesis → Settings**, set **Healthcheck Path** to `/health`.
2. Keep the web service running continuously; leave Railway Serverless/app sleeping disabled for this setup.
3. Keep one replica and `WEB_CONCURRENCY=1` initially. This limits memory use and unnecessary concurrent provider calls. The four Gunicorn threads can serve saved pages while another request runs.
4. Check that GitHub autodeploys are enabled for `main`.
5. Click **Deploy** to apply pending changes, or redeploy the latest commit after adding variables. Look at the deployment logs until the service is active. Normal startup mentions Gunicorn listening on `0.0.0.0:8080`.
6. Under **Settings → Networking → Public Networking**, click **Generate Domain**. If asked for a target port, enter `8080`.
7. Open the generated HTTPS domain. Keep this URL for testing before connecting a custom domain.

The healthcheck confirms that the application is running. It does not prove that financial data is fresh or that the database accepts writes; those are checked separately below.

## 7. Verify the deployed site

Replace `YOUR-DOMAIN` below with Railway's generated hostname.

1. Visit `https://YOUR-DOMAIN/health`. Expect `status: ok` and `version: 1.3`.
2. Visit `https://YOUR-DOMAIN/data-status`. Expect `status: ready`, model `3.0`, a snapshot identifier and coverage counts. If the package has sat unused for more than eight days, `stale` is expected until a new refresh succeeds.
3. Open **Top Opportunities**. Check its update date, **All rated companies**, **Screen matches**, **Quality watchlist**, **Partial data**, and **Unrated** views. A view can legitimately be empty.
4. Open a report and check its two scores, annual dates, peer evidence and missing-data notes. Click **Sources**, then return to the report; the snapshot stays consistent.
5. Open **Find a company**. Choose a sector or minimum Quality score and submit. Check that results match the filters. Try a combination with no matches; the site should suggest broadening the filters.
6. Open **Suggest a company**. Submit one clearly labeled test company using just its name, and note its confirmation reference. The ticker and expandable note are optional.
7. Open `https://YOUR-DOMAIN/admin/login`. Enter the `ADMIN_PASSWORD` you set. The test submission should appear under **New**.
8. Mark that submission **Reviewed**, and confirm it moves out of the New view and remains under All or Reviewed.
9. Redeploy the web service once, sign in again if necessary, and confirm the same test submission still exists. This verifies your actual Railway database connection and persistence.
10. Check the site on your phone. Keep the old hosting service until these checks and the refresh test pass.

There is no public listing of submitted company suggestions and no email sending. Owner sessions expire after one hour. Public submissions are limited to five per network address per hour; owner login attempts are limited to five per fifteen-minute window.

## 8. Activate and test the weekly refresh

**Hosting the website and running the weekly refresh are two separate pieces.** The supplied workflow runs on GitHub, writes validated snapshots to the repository, and pushes a commit. Railway's GitHub autodeploy then builds the new snapshot into the website.

1. Open the `ThesisRailway` repository on GitHub.
2. Go to **Settings → Actions → General**. Enable Actions for this repository if needed. Under **Workflow permissions**, allow **Read and write permissions** if the account's policy permits it. The workflow explicitly requests `contents: write`.
3. If branch protection blocks automation pushes, use an approved deployment branch/workflow arrangement. Do not remove unrelated protection rules blindly. A rejected push means Railway will keep the old snapshot even if the data collection itself succeeded.
4. Open the **Actions** tab and choose **Weekly company refresh**.
5. Click **Run workflow**, choose `main`, and click **Run workflow** again.
6. Open the run. It installs locked dependencies, runs the tests against a disposable PostgreSQL test database, fetches the 109-company universe, validates coverage, saves diagnostics, and commits the snapshot. It does not connect to your Railway submission database.
7. Allow time for the paced provider scan. The job has a 110-minute timeout and a 90-minute collection budget; actual runtime depends on provider responses. Do not start multiple overlapping refreshes. Complete inputs are not fetched again during the retry pass.
8. Confirm the run succeeds, including **Publish snapshot to deployment branch**. A `published` diagnostic alone is not proof that the push or Railway deployment succeeded.
9. Confirm a new `Refresh weekly company research` commit appears on `main`.
10. In Railway, confirm that commit starts a successful deployment. If it does not, check the source branch, GitHub access and autodeploy setting; you can manually deploy the latest commit after fixing them.
11. Reopen `/data-status`. Its snapshot identifier must match the newly committed `data/recommendations.json`, and its date should have advanced. Then check the Top Opportunities page.

After this test, the YAML schedule requests a refresh **every Sunday at 23:17 UTC**. GitHub schedules can be delayed, so that is a requested start time, not an exact publication deadline. The workflow must remain on the default branch. Public repositories can have schedules disabled after 60 days of inactivity; this guide uses a private repository, but you should still monitor workflow failures and account limits.

You do not need an additional Railway cron service for this design. A separate cron process writing to its own container would not update the web service's bundled files automatically.

## 9. What a successful refresh means

For the 109-company universe, publication requires at least **88 reports returned** and **66 companies with both complete scores**. Peer comparisons are computed from the collected dataset before those checks. The strict investment screen is not relaxed to fill a list.

The process saves reports and sanitized request diagnostics as it runs. It retries incomplete companies once after a pause, stops on an observed rate-limit response, and never merges incompatible partial attempts into a complete report. A failed validation or publication leaves the prior current snapshot intact. Historical snapshots support consistent older report links.

At eight days old the app flags a snapshot as stale and `/data-status` returns HTTP 503; the rest of the site stays available. `/health` remains separate, so an upstream-data problem does not repeatedly restart an otherwise working app.

Enable GitHub Actions failure notifications for your account. Check `/data-status` after weekly runs, or connect an uptime monitor to that path if you want alerts about stale data. The code supports these checks; no monitoring account or notification service has been created for you.

## 10. Manage suggested companies

1. Sign in at `/admin/login`.
2. Review the New inbox and use **Reviewed**, **Shortlisted**, or **Dismissed** to keep it organized.
3. Shortlisting does not automatically alter scores or coverage. Verify the ticker, business type and provider availability first.
4. To add a supported company, edit `universe.json` in GitHub, adding its exact ticker inside the JSON list. Preserve commas and quotation marks and avoid duplicates.
5. Commit the change and manually run **Weekly company refresh**. The company appears in the next successfully published snapshot if usable data is available, otherwise with an unrated explanation.
6. Keep a useful comparison sample. Removing too many peers can make a company's peer-based factors unscorable.

## 11. Fix common setup problems

| What you see | What to check |
| --- | --- |
| Build cannot find requirements or `app.py` | Application files may be one folder too deep. Fix the repository root or correct Railway's Root Directory. |
| Application failed to respond | Check deployment logs, `PORT=8080`, target port 8080 and the included Gunicorn command. |
| Suggestion form is unavailable | Confirm the web service has `THESIS_ENV`, a long enough `SECRET_KEY`, and the Postgres `DATABASE_URL` reference; redeploy pending variables. |
| “We could not save your suggestion” | Confirm PostgreSQL is running, its volume is attached, and `DATABASE_URL` resolves to the database in the same project/environment. Do not replace it with a local filesystem path. |
| Owner access is not configured | Check `ADMIN_PASSWORD` is at least 16 characters, and the session secret and storage are configured. Redeploy. |
| Form expired | Reload the page to get a fresh form token. Use the HTTPS domain, especially in production. |
| Data refresh failed with 429/rate limit | Keep the last good snapshot. Wait before a later manual retry; avoid repeatedly hammering the provider. |
| Coverage below 80%/60% | Inspect the run summary and diagnostic artifact for failed symbols, stale statements or missing peers. Repair the cause; do not lower the checks simply to publish. |
| Actions cannot push | Check write permissions and branch protection. Data fetched in a failed run is not yet deployed. |
| New commit exists but website date did not change | Check Railway's deployed commit, connected branch and autodeploy status, then `/data-status`. |
| No strict screen matches | This is permitted. Use All rated companies, Quality watchlist and the finder. The app does not invent qualifying companies. |

## 12. Finish the move

Once the domain, submission persistence and refresh deployment all pass, optionally add your custom domain under Railway's Networking settings and follow the exact DNS records Railway provides. Keep the old service available until the new domain is verified. You can then decide whether to stop the old hosting subscription.

For a code rollback, redeploy a known-good commit in Railway. That does not roll back the PostgreSQL inbox. Restore database content only from a deliberately chosen backup; do not delete the database service to roll back application code.

## Official references checked

- [Deploy Flask on Railway](https://docs.railway.com/guides/flask)
- [Railway PostgreSQL](https://docs.railway.com/databases/postgresql)
- [Variables and references](https://docs.railway.com/variables)
- [Reference variables and deployment order](https://docs.railway.com/deployments/deployment-actions)
- [GitHub autodeploys](https://docs.railway.com/deployments/github-autodeploys)
- [Railway healthchecks](https://docs.railway.com/deployments/healthchecks)
- [Railway pricing](https://docs.railway.com/pricing)
- [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Run a workflow manually](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

Railway and GitHub may adjust interface labels after this guide's preparation date. The architecture and the included application settings above are specific to this package.
