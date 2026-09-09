import shutil
import subprocess

from fastapi.testclient import TestClient

from codex_harbor.api import create_app


def test_desktop_assets_and_health(repository):
    client = TestClient(create_app(repository), base_url="http://127.0.0.1")
    assert client.get("/api/health").json()["application"] == "codex-harbor"
    for name, mime in [
        ("harbor.svg", "image/svg+xml"),
        ("desktop.css", "text/css"),
        ("desktop.js", "javascript"),
    ]:
        response = client.get("/assets/" + name)
        assert response.status_code == 200
        assert mime in response.headers["content-type"]
    assert client.get("/assets/desktop.py").status_code == 404
    node = shutil.which("node")
    if node:
        checked = subprocess.run(
            [node, "--check"],
            input=client.get("/assets/desktop.js").text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=15,
        )
        assert checked.returncode == 0, checked.stderr
