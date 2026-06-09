FROM python:3.11-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

WORKDIR /app

COPY scraper/requirements.txt .
RUN python -m venv "$VIRTUAL_ENV" && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m playwright install --with-deps chromium && \
    chmod -R a+rX /opt/playwright-browsers

RUN groupadd --system app && \
    useradd --system --gid app --create-home app && \
    chown -R app:app /app /home/app /opt/venv

COPY --chown=app:app scraper/ .
COPY --chown=app:app shared/ ./shared/

USER app

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]
