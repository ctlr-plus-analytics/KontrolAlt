import os


_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ0ZXN0In0.signature"

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", _JWT)
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", _JWT)
os.environ.setdefault("SERP_API_KEY", "serper-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")
