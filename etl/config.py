import hashlib
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, Engine

# Chargement du fichier .env
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

# Connexions aux bases de donnees SQL Server
# fast_executemany=True permet des insertions de masse ultra-rapides en pyodbc
DW_ENGINE = create_engine(os.environ["DW_CONN"] + "?Encrypt=no&TrustServerCertificate=yes", connect_args={"fast_executemany": True})
MAG_ENGINE = create_engine(os.environ["MAG_CONN"] + "?Encrypt=no&TrustServerCertificate=yes", connect_args={"fast_executemany": True})
GRT_ENGINE = create_engine(os.environ["GRT_CONN"] + "?Encrypt=no&TrustServerCertificate=yes", connect_args={"fast_executemany": True})

# Configurations de l'ETL
CHUNK_SIZE = int(os.environ.get("ETL_CHUNK_SIZE", "5000"))
DIM_DATE_START = datetime.strptime(os.environ.get("DIM_DATE_START", "2020-01-01"), "%Y-%m-%d").date()
DIM_DATE_END = datetime.strptime(os.environ.get("DIM_DATE_END", "2025-12-31"), "%Y-%m-%d").date()


def hash_key(value: Optional[str | int | float]) -> Optional[int]:
    """
    Genere un entier unique (surrogate key) a partir d'une valeur metier (ex: CT_Num).
    Cela evite de stocker des chaines de caracteres comme cles de jointure.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    normalized = str(value).strip().upper()
    if not normalized:
        return None

    # Genere un hash SHA256 et convertit les 8 premiers octets en entier (BigInt)
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
