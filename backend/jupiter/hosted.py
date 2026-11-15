"""Single-instance cloud entry point sharing persistent files with its worker."""
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
from urllib.parse import urlsplit

LOG = logging.getLogger("jupiter.hosted")


def configure():
    database = os.environ.get("DATABASE_URL", "")
    if database.startswith(("postgres://", "postgresql://")):
        database = "postgresql+psycopg://" + database.split("://", 1)[1]
    if not database.startswith("postgresql+psycopg://"):
        raise ValueError("Configure DATABASE_URL with a PostgreSQL connection.")
    public_url = os.environ.get("APP_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")
    public = urlsplit(public_url)
    if (public.scheme != "https" or not public.hostname or public.username or public.password
            or public.path not in ("", "/") or public.query or public.fragment):
        raise ValueError("APP_PUBLIC_URL must be the public HTTPS origin.")
    port = int(os.environ.get("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT is out of range.")
    os.environ["DATABASE_URL"] = database
    os.environ["APP_ORIGINS"] = public_url.rstrip("/")
    os.environ["SECURE_COOKIES"] = "1"
    os.environ["SERVE_WEB"] = "1"
    return port


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    port = configure()
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
                   cwd=root, check=True)
    subprocess.run([sys.executable, "-m", "jupiter.seed"], cwd=root, check=True)
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda _signum, _frame: stop.set())
    children = []
    exit_code = 0
    try:
        for command in (
            [sys.executable, "-m", "jupiter.worker"],
            [sys.executable, "-m", "uvicorn", "jupiter.api:app", "--host", "0.0.0.0",
             "--port", str(port), "--no-access-log"],
        ):
            children.append(subprocess.Popen(command, cwd=root))
        LOG.info("Web application and worker started.")
        while not stop.wait(.5):
            if any(child.poll() is not None for child in children):
                LOG.error("A service exited. Restarting the application is required.")
                exit_code = 1
                break
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=25)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
