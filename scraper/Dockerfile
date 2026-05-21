FROM python:3.11-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DISPLAY=:99

# Install system dependencies for Patchright (Chromium) + Xvfb for headed mode.
# Xvfb provides a virtual framebuffer so the browser can run in headed mode
# without a physical display. This is required to bypass Cloudflare Turnstile
# managed challenges, which detect headless browsers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libxshmfence1 libxkbcommon0 libxfixes3 \
    # Xvfb virtual display + X11 font support
    xvfb x11-utils xfonts-base xauth \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python -m venv "$VIRTUAL_ENV" && \
    pip install --no-cache-dir -r requirements.txt

# Install Patchright browsers
RUN mkdir -p /ms-playwright && \
    python -m patchright install chromium && \
    groupadd --system app && \
    useradd --system --gid app --create-home app && \
    chown -R app:app /app /home/app /ms-playwright

COPY --chown=app:app . .

USER app

# xvfb-run -a starts a temporary X server on an auto-selected display number
# before running the celery command. The -s flag passes screen configuration.
# This allows Chromium to run in headed mode (BROWSER_HEADLESS=false) which
# bypasses Cloudflare's bot detection far more reliably than headless mode.
CMD ["xvfb-run", "-a", "-s", "-screen 0 1366x768x24", \
     "celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]
