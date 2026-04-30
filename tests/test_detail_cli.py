import http.server
import json
from pathlib import Path
import socketserver
import threading

from page_extractor.cli import main
from page_extractor.service import DetailCollectionService
from page_extractor.types import DetailCollectionRequest


def run_local_server(site_root: Path):
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *args,
        directory=str(site_root),
        **kwargs,
    )
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_detail_collection_service_writes_workspace_and_summary(tmp_path):
    site_root = tmp_path / "site"
    site_root.mkdir(parents=True, exist_ok=True)
    html = """
    <html>
      <head><title>Example Detail</title></head>
      <body>
        <main>
          <h1>Example Detail</h1>
          <p>Paragraph one.</p>
          <p>Paragraph two.</p>
        </main>
      </body>
    </html>
    """
    (site_root / "detail.html").write_text(html, encoding="utf-8")

    server, thread = run_local_server(site_root)
    try:
        request = DetailCollectionRequest(
            url=f"http://127.0.0.1:{server.server_address[1]}/detail.html",
            task_id="task-001",
            output_root=tmp_path,
            save_markdown=True,
            save_pdf=False,
            download_attachments=True,
        )

        summary = DetailCollectionService().collect(request)

        assert summary.status == "success"
        assert summary.task_id == "task-001"
        assert Path(summary.task_dir).exists()
        assert Path(summary.content_markdown_path).exists()
        assert Path(summary.result_summary_path).exists()
        assert Path(summary.attachments_dir).exists()
        assert (Path(summary.task_dir) / "metadata.json").exists()
        assert (Path(summary.task_dir) / "logs" / "collect.log").exists()
        markdown = Path(summary.content_markdown_path).read_text(encoding="utf-8")
        assert "# Example Detail" in markdown
        stored_summary = json.loads(Path(summary.result_summary_path).read_text(encoding="utf-8"))
        assert stored_summary["status"] == "success"
        assert stored_summary["task_id"] == "task-001"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_detail_collection_service_rejects_invalid_url(tmp_path):
    request = DetailCollectionRequest(
        url="not-a-url",
        task_id="task-invalid",
        output_root=tmp_path,
        save_markdown=True,
    )

    summary = DetailCollectionService().collect(request)

    assert summary.status == "failed"
    assert summary.error_code == "invalid_url"
    assert Path(summary.result_summary_path).exists()
    assert Path(summary.task_dir).exists()


def test_detail_cli_main_prints_json_summary(tmp_path, capsys):
    site_root = tmp_path / "site"
    site_root.mkdir(parents=True, exist_ok=True)
    html = """
    <html>
      <head><title>CLI Detail</title></head>
      <body><article><p>CLI paragraph.</p></article></body>
    </html>
    """
    (site_root / "detail.html").write_text(html, encoding="utf-8")

    server, thread = run_local_server(site_root)
    try:
        exit_code = main([
            "collect",
            "--url",
            f"http://127.0.0.1:{server.server_address[1]}/detail.html",
            "--task-id",
            "task-cli",
            "--output-root",
            str(tmp_path),
            "--format",
            "json",
            "--save-markdown",
        ])

        captured = capsys.readouterr()
        payload = json.loads(captured.out.strip())

        assert exit_code == 0
        assert payload["status"] == "success"
        assert payload["task_id"] == "task-cli"
        assert Path(payload["result_summary_path"]).exists()
        assert Path(payload["content_markdown_path"]).exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
