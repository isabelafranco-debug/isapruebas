import pytest

from jupiter.hosted import configure


def test_hosted_configures_https_and_psycopg(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@db/jupiter")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://jupiter-test.onrender.com")
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    monkeypatch.setenv("PORT", "10000")
    for name in ("APP_ORIGINS", "SECURE_COOKIES", "SERVE_WEB"):
        monkeypatch.setenv(name, "old")
    assert configure() == 10000
    import os
    assert os.environ["DATABASE_URL"] == "postgresql+psycopg://user:password@db/jupiter"
    assert os.environ["APP_ORIGINS"] == "https://jupiter-test.onrender.com"
    assert os.environ["SECURE_COOKIES"] == "1"
    assert os.environ["SERVE_WEB"] == "1"


@pytest.mark.parametrize("origin", ["http://example.org", "https://example.org/path", "https://u:p@example.org"])
def test_hosted_rejects_invalid_public_origin(monkeypatch, origin):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db/jupiter")
    monkeypatch.setenv("APP_PUBLIC_URL", origin)
    with pytest.raises(ValueError, match="HTTPS origin"):
        configure()
