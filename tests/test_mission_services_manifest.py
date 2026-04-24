from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backend_manifest_uses_windows_background_start_script():
    manifest = (ROOT / ".factory" / "services.yaml").read_text()

    assert "  backend:" in manifest
    assert "port: 8000" in manifest
    assert "start: powershell -NoProfile -ExecutionPolicy Bypass -File D:\\WY-DATASETS\\sea-data\\.factory\\start_backend.ps1" in manifest
    assert "healthcheck: curl -sf http://127.0.0.1:8000/" in manifest
    assert "LocalPort 8000" in manifest


def test_windows_backend_start_script_has_readiness_and_log_capture():
    script = (ROOT / ".factory" / "start_backend.ps1").read_text()

    assert "Start-Process" in script
    assert "-RedirectStandardOutput $LogFile" in script
    assert "-RedirectStandardError $LogFile" in script
    assert "Invoke-WebRequest" in script
    assert "http://127.0.0.1:$Port/" in script
    assert "$Port = 8000" in script
    assert "Backend did not become healthy within 30 seconds" in script
