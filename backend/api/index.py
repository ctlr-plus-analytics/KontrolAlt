"""Vercel serverless entry point for FastAPI backend."""

import sys
from pathlib import Path

# Ensure backend root directory is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from main import app  # noqa: E402
