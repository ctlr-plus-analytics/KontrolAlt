FROM python:3.11-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DISPLAY=:99

# Install system dependencies for Xvfb for headed mode support.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Xvfb virtual display + X11 font support
    xvfb x11-utils xfonts-base xauth \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python -m venv "$VIRTUAL_ENV" && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m playwright install-deps firefox

RUN groupadd --system app && \
    useradd --system --gid app --create-home app && \
    chown -R app:app /app /home/app /opt/venv

COPY --chown=app:app . .

USER app

# Fetch Camoufox binary as the app user to put it in their home directory cache
RUN python -m camoufox fetch

# xvfb-run -a starts a temporary X server on an auto-selected display number
# before running the celery command.
CMD ["xvfb-run", "-a", "-s", "-screen 0 1366x768x24", \
     "celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]
