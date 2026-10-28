"""Portable production settings; Railway supplies PORT."""
import os

bind = "0.0.0.0:" + os.environ.get("PORT", "8080")
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = 4
timeout = 120
accesslog = "-"
errorlog = "-"
capture_output = True
