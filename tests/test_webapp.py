"""
Tests for the FastAPI skeleton (webapp/main.py) — TestClient drives the app
in-process (no real Uvicorn socket needed), so this runs offline like the
rest of the suite.
"""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from SSP.webapp.main import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_bare_address_redirects_to_upload():
    # Typing the portal's hostname or IP with no path used to 404.
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/upload"


def test_docs_availability_matches_config():
    # app.docs_url is fixed at import time from config.docs_enabled, so
    # rather than fake a different .env mid-test, just assert the live
    # app's /docs status agrees with whatever the current config says.
    from SSP.config import get_config

    expected_status = 200 if get_config().docs_enabled else 404
    assert client.get("/docs").status_code == expected_status


# The hotspot gives phones no internet (ADR 0007), so a portal page that
# loads anything from outside stalls until the request fails.
TEMPLATES = Path(__file__).resolve().parent.parent / "SSP" / "webapp" / "templates"
EXTERNAL_REF = re.compile(r"""(?:src|href|action)\s*=\s*["']?(?:https?:)?//|url\(\s*["']?(?:https?:)?//|@import""")


def test_portal_pages_load_nothing_from_the_internet():
    for page in TEMPLATES.glob("*.html"):
        assert not EXTERNAL_REF.search(page.read_text(encoding="utf-8")), page.name


def test_every_included_icon_exists():
    for page in TEMPLATES.glob("*.html"):
        for name in re.findall(r'{%\s*include\s+"(icons/[^"]+)"\s*%}', page.read_text(encoding="utf-8")):
            assert (TEMPLATES / name).is_file(), f"{page.name}: {name}"


def test_upload_page_renders_icons_inline():
    response = client.get("/upload")
    assert response.status_code == 200
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in response.text
    assert "font-awesome" not in response.text
