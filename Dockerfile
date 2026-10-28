FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && useradd --create-home --uid 10001 thesis
COPY --chown=thesis:thesis . .
USER thesis

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
