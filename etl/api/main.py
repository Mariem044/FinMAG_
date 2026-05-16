from __future__ import annotations

import logging
import os

# to read the env 
from dotenv import load_dotenv

# apis existant in queries 
from fastapi import FastAPI

# this used to import google generative ai but itês actually used in queries 
try:
    from google import genai
except ImportError:  # pragma: no cover - depends on installed Gemini package variant
    genai = None


load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# This file is for imports only
