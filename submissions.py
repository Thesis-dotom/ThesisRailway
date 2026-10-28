"""Private company suggestions, with PostgreSQL persistence in production."""
from contextlib import contextmanager
from functools import wraps
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3
import time
from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

bp = Blueprint('submissions', __name__)
STATUSES = {'new', 'reviewed', 'shortlisted', 'dismissed'}


def configured():
    app = current_app
    return bool(app.secret_key and (app.config.get('DATABASE_URL') or
                (not app.config.get('PRODUCTION') and app.config.get('SUGGESTIONS_DB_PATH'))))


class Database:
    def __init__(self, connection, postgres):
        self.connection, self.postgres = connection, postgres

    def execute(self, sql, params=()):
        return self.connection.execute(sql if self.postgres else sql.replace('%s', '?'), params)


@contextmanager
def database():
    if not configured():
        raise RuntimeError('Submission storage is not configured')
    url = current_app.config.get('DATABASE_URL')
    if url:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(url, connect_timeout=5, row_factory=dict_row)
    else:
        path = Path(current_app.config['SUGGESTIONS_DB_PATH'])
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
    db = Database(conn, bool(url))
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS company_suggestions (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, company TEXT NOT NULL,
            ticker TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
            updated_at TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS request_limits (
            key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at BIGINT NOT NULL)''')
        yield db
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def csrf_token():
    if not current_app.secret_key:
        return ''
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


def valid_csrf():
    supplied, expected = request.form.get('csrf_token', ''), session.get('csrf', '')
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))


def consume_limit(db, purpose, limit, seconds):
    now = int(time.time())
    bucket = now // seconds
    address = request.remote_addr or 'unknown'
    key = hmac.new(current_app.secret_key.encode(), f'{purpose}:{address}:{bucket}'.encode(), hashlib.sha256).hexdigest()
    row = db.execute('''INSERT INTO request_limits (key,count,expires_at) VALUES (%s,1,%s)
        ON CONFLICT(key) DO UPDATE SET count=request_limits.count+1 RETURNING count''', (key, (bucket+1)*seconds)).fetchone()
    db.execute('DELETE FROM request_limits WHERE expires_at < %s', (now-86400,))
    return row['count'] <= limit


def timestamp():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    return ' '.join(''.join(c for c in value if c.isprintable() or c.isspace()).split())


def is_admin():
    return bool(current_app.config.get('ADMIN_PASSWORD_HASH') and session.get('admin') and time.time()-session.get('auth_at', 0) <= 3600
                and session.get('admin_version') == current_app.config.get('ADMIN_AUTH_VERSION'))


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not is_admin():
            return redirect(url_for('submissions.login'))
        return fn(*args, **kwargs)
    return wrapped


@bp.app_context_processor
def form_context():
    return {'csrf_token': csrf_token}


@bp.after_request
def private_pages(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@bp.route('/suggest-company', methods=['GET', 'POST'])
def suggest_company():
    enabled = configured()
    values = {key: '' for key in ['company', 'ticker', 'reason']}
    error, code = None, 200
    submitted = request.args.get('submitted', '')
    submitted = submitted if re.fullmatch(r'[a-f0-9]{12}', submitted) and submitted == session.get('last_submission') else ''
    if request.method == 'POST':
        if not enabled:
            error, code = 'Company suggestions are temporarily unavailable. Please try again later.', 503
        elif not valid_csrf():
            error, code = 'This form expired. Reload the page and try again.', 400
        elif request.form.get('website'):
            error, code = 'Please reload this form and submit it again.', 400
        else:
            values = {key: clean_text(request.form.get(key, '')) for key in values}
            values['ticker'] = values['ticker'].upper()
            if not 2 <= len(values['company']) <= 120:
                error, code = 'Enter a company name between 2 and 120 characters.', 400
            elif values['ticker'] and not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,14}', values['ticker']):
                error, code = 'Enter a valid ticker, or leave it blank.', 400
            elif len(values['reason']) > 2000:
                error, code = 'Keep your optional note to 2,000 characters or fewer.', 400
            else:
                try:
                    with database() as db:
                        allowed = consume_limit(db, 'suggestion', 5, 3600)
                        if allowed:
                            identifier, now = secrets.token_hex(6), timestamp()
                            db.execute('INSERT INTO company_suggestions VALUES (%s,%s,%s,%s,%s,%s,%s)',
                                       (identifier,now,values['company'],values['ticker'],values['reason'],'new',now))
                    if not allowed:
                        error, code = 'You have reached the hourly suggestion limit. Please try again later.', 429
                    else:
                        session['last_submission'] = identifier
                        return redirect(url_for('submissions.suggest_company', submitted=identifier), code=303)
                except Exception:
                    current_app.logger.warning('Company suggestion storage operation failed')
                    error, code = 'We could not save your suggestion. Please try again later.', 503
    return render_template('suggest_company.html', enabled=enabled, values=values,
                           error=error, submitted=submitted), code


@bp.route('/admin/login', methods=['GET', 'POST'])
def login():
    enabled = configured() and bool(current_app.config.get('ADMIN_PASSWORD_HASH'))
    error, code = None, 200
    if request.method == 'POST':
        if not enabled:
            error, code = 'Owner access is not configured.', 503
        elif not valid_csrf():
            error, code = 'This form expired. Reload the page and try again.', 400
        else:
            try:
                with database() as db:
                    allowed = consume_limit(db, 'admin-login', 5, 900)
                if not allowed:
                    error, code = 'Too many attempts. Try again in 15 minutes.', 429
                elif check_password_hash(current_app.config['ADMIN_PASSWORD_HASH'], request.form.get('password', '')):
                    session.clear()
                    session.update(admin=True, auth_at=time.time(),
                                   admin_version=current_app.config.get('ADMIN_AUTH_VERSION'))
                    return redirect(url_for('submissions.inbox'), code=303)
                else:
                    error, code = 'Incorrect password.', 401
            except Exception:
                current_app.logger.warning('Owner login storage operation failed')
                error, code = 'Owner access is temporarily unavailable.', 503
    return render_template('admin_login.html', error=error, enabled=enabled), code


@bp.route('/admin/suggestions')
@admin_required
def inbox():
    state = request.args.get('status', 'new')
    if state not in STATUSES | {'all'}:
        abort(400)
    try:
        page = max(1, int(request.args.get('page','1')))
        with database() as db:
            condition, params = ('', ()) if state=='all' else (' WHERE status=%s', (state,))
            rows = db.execute('SELECT * FROM company_suggestions'+condition+' ORDER BY created_at DESC LIMIT 51 OFFSET %s',
                              params+((page-1)*50,)).fetchall()
        return render_template('admin_inbox.html', items=[dict(r) for r in rows[:50]],
                               has_more=len(rows)>50, page=page, status=state, statuses=sorted(STATUSES))
    except ValueError:
        abort(400)
    except Exception:
        current_app.logger.warning('Suggestion inbox query failed')
        return render_template('admin_inbox.html', items=[], has_more=False, page=1,
                               status=state, statuses=sorted(STATUSES),error='The inbox is temporarily unavailable.'),503


@bp.route('/admin/suggestions/<identifier>', methods=['POST'])
@admin_required
def update_suggestion(identifier):
    if not valid_csrf() or not re.fullmatch(r'[a-f0-9]{12}',identifier):
        abort(400)
    state = request.form.get('status')
    if state not in STATUSES:
        abort(400)
    try:
        with database() as db:
            changed=db.execute('UPDATE company_suggestions SET status=%s,updated_at=%s WHERE id=%s',
                               (state,timestamp(),identifier)).rowcount
    except Exception:
        current_app.logger.warning('Suggestion status update failed')
        abort(503)
    if changed != 1:
        abort(404)
    return redirect(url_for('submissions.inbox',status='all'),code=303)


@bp.route('/admin/logout',methods=['POST'])
def logout():
    if not valid_csrf():
        abort(400)
    session.clear()
    return redirect(url_for('submissions.login'),code=303)
