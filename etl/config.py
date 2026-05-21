import os
from datetime import datetime
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Charger les variables d'environnement
load_dotenv()


def _sqlserver_tls_compat(conn_str: str) -> str:
    if not conn_str.startswith("mssql+pyodbc"):
        return conn_str

    lowered = conn_str.lower()
    if "encrypt=" in lowered or "trustservercertificate=" in lowered:
        return conn_str

    if "odbc_connect=" in lowered:
        parts = urlsplit(conn_str)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        odbc = query.get("odbc_connect")
        if odbc is None:
            return conn_str
        query["odbc_connect"] = f"{odbc};Encrypt=no;TrustServerCertificate=yes"
        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, quote_via=quote_plus),
            parts.fragment,
        ))

    sep = "&" if "?" in conn_str else "?"
    return f"{conn_str}{sep}Encrypt=no&TrustServerCertificate=yes"

# Connexions aux bases de données
def _replace_database(conn_str: str, database: str) -> str:
    if "odbc_connect=" in conn_str.lower():
        parts = urlsplit(conn_str)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        odbc = query.get("odbc_connect")
        if odbc is None:
            return conn_str

        chunks = []
        replaced = False
        for chunk in odbc.split(";"):
            if "=" not in chunk:
                chunks.append(chunk)
                continue
            key, value = chunk.split("=", 1)
            if key.strip().lower() in ("database", "initial catalog"):
                chunks.append(f"{key}={database}")
                replaced = True
            else:
                chunks.append(f"{key}={value}")
        if not replaced:
            chunks.append(f"Database={database}")

        query["odbc_connect"] = ";".join(chunks)
        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, quote_via=quote_plus),
            parts.fragment,
        ))

    parts = urlsplit(conn_str)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        f"/{database}",
        parts.query,
        parts.fragment,
    ))


def _database_name(conn_str: str) -> str | None:
    if "odbc_connect=" in conn_str.lower():
        parts = urlsplit(conn_str)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        odbc = query.get("odbc_connect")
        if not odbc:
            return None
        for chunk in odbc.split(";"):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            if key.strip().lower() in ("database", "initial catalog"):
                return value.strip() or None
        return None

    path = urlsplit(conn_str).path.strip("/")
    return path or None


def _quote_sqlserver_identifier(identifier: str) -> str:
    return f"[{identifier.replace(']', ']]')}]"


def ensure_dw_database_exists() -> None:
    """Create the target DW database when the login can access master but the DB is absent."""
    dw_conn = os.environ["DW_CONN"]
    if dw_conn.startswith("sqlite"):
        return

    db_name = _database_name(dw_conn)
    if not db_name or db_name.lower() == "master":
        return

    master_engine = create_engine(
        _sqlserver_tls_compat(_replace_database(dw_conn, "master")),
        isolation_level="AUTOCOMMIT",
    )
    with master_engine.connect() as conn:
        exists = conn.execute(text("SELECT DB_ID(:db_name)"), {"db_name": db_name}).scalar()
        if exists is None:
            conn.execute(text(f"CREATE DATABASE {_quote_sqlserver_identifier(db_name)}"))


def _make_engine(conn_str: str, *, fast_executemany: bool = False):
    kwargs = {}
    if fast_executemany and conn_str.startswith("mssql+pyodbc"):
        kwargs["fast_executemany"] = True
    return create_engine(_sqlserver_tls_compat(conn_str), **kwargs)


DW_ENGINE  = _make_engine(os.environ["DW_CONN"], fast_executemany=True)
MAG_ENGINE = _make_engine(os.environ["MAG_CONN"])
GRT_ENGINE = _make_engine(os.environ["GRT_CONN"])

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
