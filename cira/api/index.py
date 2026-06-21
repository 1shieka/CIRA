"""Vercel entry point for CIRA's FastAPI application."""

import sys
from pathlib import Path


# Vercel invokes this file from the api directory. Make the project package
# root importable so the existing FastAPI application can retain its layout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app  # noqa: E402
