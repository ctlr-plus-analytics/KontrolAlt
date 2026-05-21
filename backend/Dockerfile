FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN python -m venv "$VIRTUAL_ENV" && \
    pip install --no-cache-dir -r requirements.txt

RUN groupadd --system app && \
    useradd --system --gid app --create-home app

COPY --chown=app:app . .

USER app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
