from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI

try:
    from google import genai
except ImportError:  # pragma: no cover - depends on installed Gemini package variant
    genai = None


load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

app = FastAPI(title="FinMAG API")
_startup_logger = logging.getLogger("api.startup")

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if _GEMINI_API_KEY and genai is not None:
    _GEMINI_CLIENT = genai.Client(api_key=_GEMINI_API_KEY)
    _LLM_READY = True
    _startup_logger.info("Gemini LLM ready.")
else:
    _GEMINI_CLIENT = None
    _LLM_READY = False
    _startup_logger.warning(
        "GEMINI_API_KEY not set or Gemini SDK unavailable - LLM assistant disabled. "
        "Add GEMINI_API_KEY to etl/.env and install the Gemini SDK to enable it."
    )


@app.get("/api/assistant/status")
def get_assistant_status():
    return {"llm_ready": _LLM_READY, "model": "gemini-1.5-flash" if _LLM_READY else None}
