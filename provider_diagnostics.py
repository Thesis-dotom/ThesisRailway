"""Bounded, sanitized diagnostics for an isolated refresh worker.

This adapter targets the yfinance version pinned in requirements.lock. It runs
only in a single-company subprocess, never in the threaded web server.
"""
import time
from urllib.parse import urlsplit


class ProviderDiagnostics:
    def __init__(self, delay=0.5):
        self.delay = delay
        self.requests = []
        self.rate_limited = False

    def __enter__(self):
        from yfinance.data import YfData
        from yfinance.exceptions import YFRateLimitError

        self.original = YfData.get
        observer = self

        def get(data, url, *args, **kwargs):
            # yfinance can swallow exceptions while loading statements. Once a
            # 429 is observed, do not make more provider requests in this worker.
            if observer.rate_limited:
                raise YFRateLimitError()
            if observer.requests:
                time.sleep(observer.delay)
            event = {"path": urlsplit(url).path}
            try:
                response = observer.original(data, url, *args, **kwargs)
                event["http_status"] = response.status_code
                if response.status_code == 429:
                    observer.rate_limited = True
                return response
            except Exception as exc:
                event["error_type"] = type(exc).__name__
                if isinstance(exc, YFRateLimitError):
                    observer.rate_limited = True
                raise
            finally:
                # Never record cookies, tokens, query strings, or response bodies.
                observer.requests.append(event)

        YfData.get = get
        return self

    def __exit__(self, *_):
        from yfinance.data import YfData
        YfData.get = self.original
