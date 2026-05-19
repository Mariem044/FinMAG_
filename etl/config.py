import os
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Charger les variables d'environnement
load_dotenv()

# Connexions aux bases de données
DW_ENGINE  = create_engine(os.environ["DW_CONN"]  + "?Encrypt=no&TrustServerCertificate=yes", fast_executemany=True)
MAG_ENGINE = create_engine(os.environ["MAG_CONN"] + "?Encrypt=no&TrustServerCertificate=yes")
GRT_ENGINE = create_engine(os.environ["GRT_CONN"] + "?Encrypt=no&TrustServerCertificate=yes")

# Paramètres ETL
DIM_DATE_START = datetime.strptime(os.environ.get("DIM_DATE_START", "2020-01-01"), "%Y-%m-%d").date()
DIM_DATE_END   = datetime.strptime(os.environ.get("DIM_DATE_END",   "2026-12-31"), "%Y-%m-%d").date()

# Paramètres supplémentaires
AUDIT_TABLE_NAME = os.environ.get("ETL_AUDIT_TABLE", "ETL_AUDIT")
CHUNK_SIZE = int(os.environ.get("ETL_CHUNK_SIZE", "5000"))
ERROR_MSG_MAX_LEN = int(os.environ.get("ETL_ERROR_MSG_MAX_LEN", "500"))


def hash_key(value) -> int | None:
    """Retourne un entier positif 31-bit déterministe, ou None si vide."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if not s:
        return None
    import hashlib
    digest = hashlib.md5(s.encode()).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF
