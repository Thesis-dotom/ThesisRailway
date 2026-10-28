"""Exercise real persistence and request security on SQLite and, in CI, PostgreSQL."""
import os
import re
import time
import pytest
from werkzeug.security import generate_password_hash
import app as thesis
import submissions

PASSWORD = 'test-owner-password-unique-2026'
BACKENDS = ['sqlite'] + (['postgres'] if os.getenv('DATABASE_TEST_URL') else [])

@pytest.fixture(params=BACKENDS)
def client(request, tmp_path, monkeypatch):
    config = {'TESTING':True, 'SECRET_KEY':'test-secret-' * 5, 'PRODUCTION':False,
              'DATABASE_URL':'', 'SUGGESTIONS_DB_PATH':str(tmp_path/'suggestions.sqlite3'),
              'SESSION_COOKIE_SECURE':False, 'ADMIN_PASSWORD_HASH':generate_password_hash(PASSWORD),
              'ADMIN_AUTH_VERSION':'test-owner-version'}
    if request.param == 'postgres':
        import psycopg
        from urllib.parse import urlsplit
        url = os.environ['DATABASE_TEST_URL']
        if urlsplit(url).path != '/thesis_test':
            pytest.fail('Integration tests require a disposable database named thesis_test')
        config.update(DATABASE_URL=url, PRODUCTION=True)
        with psycopg.connect(url) as connection:
            connection.execute('DROP TABLE IF EXISTS company_suggestions, request_limits')
    for key,value in config.items():
        monkeypatch.setitem(thesis.app.config,key,value)
    return thesis.app.test_client()


def token(client, path='/suggest-company'):
    assert client.get(path).status_code == 200
    with client.session_transaction() as session:
        return session['csrf']


def submit(client, **changes):
    payload = {'csrf_token':token(client), 'company':'Example Incorporated', 'ticker':'EXMP',
               'reason':'Please research its cash flow and long-term business prospects.'}
    payload.update(changes)
    return client.post('/suggest-company',data=payload)


def login(client):
    return client.post('/admin/login',data={'csrf_token':token(client,'/admin/login'),'password':PASSWORD})


def rows():
    with thesis.app.app_context(), submissions.database() as db:
        return [dict(r) for r in db.execute('SELECT * FROM company_suggestions').fetchall()]


def test_submission_persists_and_is_private(client):
    response=submit(client)
    assert response.status_code==303
    saved=rows()
    assert len(saved)==1 and saved[0]['ticker']=='EXMP' and saved[0]['status']=='new'
    assert b'Suggestion received' in client.get(response.location).data
    other=thesis.app.test_client()
    assert other.get('/admin/suggestions').status_code==302
    assert saved[0]['reason'].encode() not in other.get('/suggest-company').data
    # A new HTTP session reads the same persisted database after authenticating.
    assert login(other).status_code==303
    assert saved[0]['reason'].encode() in other.get('/admin/suggestions').data


def test_csrf_validation_and_input_limits(client):
    assert submit(client,csrf_token='wrong').status_code==400
    assert submit(client,reason='a'*2001).status_code==400
    assert submit(client,ticker='BAD <script>').status_code==400
    assert submit(client,company='').status_code==400
    assert rows()==[]
    assert client.post('/suggest-company',data={'reason':'a'*17000}).status_code==413


def test_company_name_only_and_optional_short_note(client):
    response=client.post('/suggest-company',data={'csrf_token':token(client),'company':'Name Only Company'})
    assert response.status_code==303
    saved=rows()
    assert len(saved)==1 and saved[0]['reason']=='' and saved[0]['ticker']==''
    assert b'Suggestion received' in client.get(response.location).data
    assert login(client).status_code==303
    assert b'No note added.' in client.get('/admin/suggestions').data
    assert submit(client,reason='Just curious').status_code==303
    assert any(r['reason']=='Just curious' for r in rows())


def test_submission_rate_limit_and_honeypot(client):
    assert submit(client,website='spam.example').status_code==400
    assert rows()==[]
    assert b'Suggestion received' not in client.get('/suggest-company?submitted=012345abcdef').data
    for _ in range(5): assert submit(client).status_code==303
    assert submit(client).status_code==429
    assert len(rows())==5


def test_admin_auth_status_and_escaping(client):
    assert submit(client,company='<script>alert(1)</script>').status_code==303
    identifier=rows()[0]['id']
    assert client.post('/admin/suggestions/'+identifier,data={'status':'shortlisted'}).status_code==302
    assert login(client).status_code==303
    page=client.get('/admin/suggestions')
    assert page.headers['Cache-Control']=='no-store'
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;' in page.data
    assert b'<script>alert(1)</script>' not in page.data
    assert client.post('/admin/suggestions/'+identifier,data={'status':'shortlisted'}).status_code==400
    csrf=token(client,'/admin/suggestions')
    response=client.post('/admin/suggestions/'+identifier,data={'status':'shortlisted','csrf_token':csrf})
    assert response.status_code==303 and rows()[0]['status']=='shortlisted'
    assert b'alert(1)' not in client.get('/admin/suggestions?status=new').data
    assert client.post('/admin/suggestions/'+'0'*12,data={'status':'reviewed','csrf_token':csrf}).status_code==404
    assert client.post('/admin/logout',data={'csrf_token':csrf}).status_code==303
    assert client.get('/admin/suggestions').status_code==302


def test_admin_expiry_and_login_rate_limit(client):
    csrf=token(client,'/admin/login')
    for _ in range(5):
        assert client.post('/admin/login',data={'csrf_token':csrf,'password':'incorrect'}).status_code==401
    assert client.post('/admin/login',data={'csrf_token':csrf,'password':PASSWORD}).status_code==429
    with client.session_transaction() as session:
        session.update(admin=True,auth_at=time.time()-3601,admin_version='test-owner-version')
    assert client.get('/admin/suggestions').status_code==302


def test_failed_write_is_never_reported_as_saved(client,monkeypatch):
    def unavailable(): raise RuntimeError('Storage unavailable')
    monkeypatch.setattr(submissions,'database',unavailable)
    response=submit(client)
    assert response.status_code==503
    assert b'could not save' in response.data
    assert b'Suggestion received' not in response.data


def test_production_requires_durable_storage(client,monkeypatch):
    monkeypatch.setitem(thesis.app.config,'PRODUCTION',True)
    monkeypatch.setitem(thesis.app.config,'DATABASE_URL','')
    assert client.get('/suggest-company').status_code==200
    assert client.post('/suggest-company',data={}).status_code==503
    assert client.post('/admin/login',data={}).status_code==503
