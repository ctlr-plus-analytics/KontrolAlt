# Kontrol_Alt — Intelligence & Discovery Engine

Kontrol_Alt is an intelligence and discovery engine that scrapes alternative media platforms (Rumble and BitChute), computes creator growth velocity metrics, runs automated compliance checks, and presents findings on a dashboard for a talent hunting team. It combines a Next.js 14 frontend, FastAPI backend, and Patchright-powered scraper orchestrated via Celery.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | 18+ | Frontend runtime |
| npm | 9+ | Frontend package management |
| Python | 3.11+ | Backend & scraper runtime |
| pip | 23+ | Python package management |
| Docker & Docker Compose | latest | Redis, backend, worker containers |
| Supabase account | — | Cloud-hosted PostgreSQL + Auth |
| Serper account | — | Gate 0 search API key |

---

## Local Setup

### 1. Clone & Configure Environment

```bash
git clone <repo-url> kontrol-alt
cd kontrol-alt
cp .env.example .env
# Fill in all values in .env
```

### 2. Start Infrastructure (Redis)

```bash
docker compose up redis -d
```

### 3. Backend (FastAPI)

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
# source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The backend will be available at `http://localhost:8000`. Health check: `GET http://localhost:8000/health`.

### 4. Scraper & Celery Worker

```bash
cd scraper
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
# source venv/bin/activate
pip install -r requirements.txt
```

**Start the Celery worker:**

```bash
celery -A worker.celery_app worker --loglevel=info
```

**Start the Celery Beat scheduler (separate terminal):**

```bash
celery -A worker.celery_app beat --loglevel=info
```

### 5. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:3000`.

---

## Docker Compose (Full Stack minus Frontend)

To run the backend, worker, and beat scheduler together:

```bash
docker compose up --build
```

> **Note:** The frontend runs locally via `npm run dev` and is excluded from Docker. Supabase is cloud-hosted and also excluded.

---

## Database Migration

1. Open the [Supabase Dashboard](https://supabase.com/dashboard) for your project.
2. Navigate to **SQL Editor**.
3. Copy the contents of `database/migrations/001_initial_schema.sql`.
4. Paste and run the SQL in the editor.
5. Verify all 7 tables are created under the **Table Editor**.

Alternatively, use the Supabase CLI:

```bash
supabase db push --db-url "postgresql://postgres:<password>@<host>:5432/postgres" < database/migrations/001_initial_schema.sql
```

---

## Environment Variable Reference

| Variable | Service | Required | Description |
|----------|---------|----------|-------------|
| `SUPABASE_URL` | Backend, Scraper | Yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | Backend | Yes | Supabase anonymous API key |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend, Scraper | Yes | Supabase service role key |
| `SERP_API_KEY` | Backend, Scraper | Yes | Serper API key for Gate 0 search |
| `REDIS_URL` | Backend, Scraper | Yes | Redis connection URL |
| `PROXY_LIST` | Scraper | Yes | Comma-separated proxy strings |
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend | Yes | Supabase URL (public) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend | Yes | Supabase anon key (public) |
| `NEXT_PUBLIC_API_URL` | Frontend | Yes | Backend API base URL |
| `FRONTEND_ORIGIN` | Backend | Yes | Frontend URL for CORS |

---

## Project Structure

```
kontrol-alt/
├── frontend/          # Next.js 14 TypeScript app
├── backend/           # FastAPI app
├── scraper/           # Patchright scraper & Celery worker
├── shared/            # Shared TypeScript types
├── database/          # SQL migrations
├── .env.example       # Environment variable template
├── docker-compose.yml # Container orchestration
└── README.md          # This file
```
