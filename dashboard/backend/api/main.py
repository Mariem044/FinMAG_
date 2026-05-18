from __future__ import annotations

import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI

try:
    from google import genai
except ImportError:
    genai = None

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
