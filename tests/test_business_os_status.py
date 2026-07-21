from pathlib import Path
import subprocess

from ops import business_os_server


def test_status_endpoint_shape(monkeypatch):
    monkeypatch.setattr(business_os_server, "_postgres_status", lambda: "ok")
    monkeypatch.setattr(business_os_server, "_nocodb_status", lambda: "ok")
    monkeypatch.setattr(business_os_server, "_module_status", lambda _name: "ok")
    monkeypatch.setattr(business_os_server, "_version", lambda: "test-version")

    response = business_os_server.app.test_client().get("/status")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "running"
    assert payload["version"] == "test-version"
    assert set(payload) == {
        "status", "uptime", "postgres", "nocodb", "formula_engine",
        "receive_payment", "voucher_engine", "inventory", "version",
    }


def test_launchagent_environment_imports_receive_payment_server():
    root = Path(__file__).resolve().parents[1]
    wrapper = (root / "ops/businessos-service.sh").read_text()
    assert 'export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"' in wrapper
    assert 'cd "$PROJECT_ROOT" || exit 1' in wrapper

    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONPATH": str(root),
        "RECEIVE_PAYMENT_HOST": "0.0.0.0",
        "RECEIVE_PAYMENT_PORT": "5059",
    }
    result = subprocess.run(
        ["/usr/bin/python3", "-c", "import scripts.receive_payment_server; print('import-ok')"],
        cwd="/tmp", env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "import-ok"
    assert "PYTHONHOME" not in environment
