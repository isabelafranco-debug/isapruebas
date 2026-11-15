"""Build a portable source ZIP with the current frontend build."""
import hashlib
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", ".local", ".venv", ".pytest_cache", "__pycache__", "node_modules", "deliverables"}


def main():
    destination = ROOT / "deliverables"
    destination.mkdir(exist_ok=True)
    archive = destination / "Jupiter-Jr-proyecto.zip"
    files = []
    for folder, directories, names in os.walk(ROOT):
        directories[:] = sorted(d for d in directories if d not in EXCLUDED)
        for name in sorted(names):
            if (name == ".env.example" or not name.startswith(".env")) and not name.endswith((".pyc", ".log", ".pid")):
                files.append(Path(folder) / name)
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            output.write(path, "Jupiter-Jr/" + path.relative_to(ROOT).as_posix())
    with ZipFile(archive) as output:
        if output.testzip() is not None:
            raise RuntimeError("The ZIP integrity check failed.")
        names = set(output.namelist())
        for required in ("Dockerfile", "render.yaml", "README.md", "PUBLICAR.md", "web/dist/index.html"):
            if "Jupiter-Jr/" + required not in names:
                raise RuntimeError(f"The ZIP is missing {required}.")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
    print(f"ZIP verified: {archive} ({archive.stat().st_size:,} bytes)")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
