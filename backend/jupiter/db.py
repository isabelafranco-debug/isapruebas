import os
from pathlib import Path
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
STORAGE = Path(os.getenv("PRIVATE_STORAGE", str(ROOT / ".local" / "private"))).resolve()
STORAGE.mkdir(parents=True, exist_ok=True)
PILOT_CSV = ROOT / "data/reference/NASA_POWER_PT_priner_2015_2025.csv"
PILOT = [-63.272578418254845, -17.182537861479094]
PILOT_SHA = "a857c75725241b54619b2552f86ec488627b222cafd3f70b33a791115c3f306d"

PORTABLE = os.getenv("JUPITER_WINDOWS_PORTABLE") == "1"
engine = create_engine(
    os.getenv("DATABASE_URL", "postgresql+psycopg://jupiter@127.0.0.1:55432/jupiter"),
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None} if PORTABLE else {},
)

def query(conn, sql, **params):
    return conn.execute(text(sql), params)

def one(conn, sql, **params):
    return query(conn, sql, **params).mappings().first()

def many(conn, sql, **params):
    return [dict(row) for row in query(conn, sql, **params).mappings()]
