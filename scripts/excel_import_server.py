import os
import sys
import csv
import io
import secrets
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, Response, jsonify, request, send_file

from tools.excel_importer import import_excel_payload
from tools.veggies_production import (
    import_veggies_preview,
    load_crop_definitions,
    parse_veggies_workbook,
)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
_VEGGIES_PREVIEWS = {}
VEGGIES_TEMPLATE = Path(PROJECT_ROOT) / "excel_import" / "BigShot_Veggies_Production_Template.xlsx"


IMPORT_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BigShot Business Data Import</title>
  <style>
    :root { --green:#174f3b; --soft:#e4f0ea; --bg:#f3f5f4; --text:#17211c; --line:#dfe5e2; }
    * { box-sizing:border-box; } body { margin:0; font:14px Arial,sans-serif; background:var(--bg); color:var(--text); }
    main { width:min(900px,calc(100% - 32px)); margin:40px auto; }
    .card { background:white; border:1px solid var(--line); border-radius:14px; padding:28px; box-shadow:0 10px 28px rgba(20,44,33,.06); }
    h1 { margin:0 0 8px; color:var(--green); } p { line-height:1.55; }
    label { display:grid; gap:7px; margin:18px 0; font-weight:700; }
    select,input,button,a.button { width:100%; padding:11px 12px; border:1px solid var(--line); border-radius:8px; background:white; color:inherit; }
    button,a.button { display:inline-block; width:auto; background:var(--green); color:white; border:0; font-weight:700; cursor:pointer; text-decoration:none; }
    button[disabled] { opacity:.55; cursor:wait; } #result { white-space:pre-wrap; background:#f7f9f8; border-radius:8px; padding:16px; min-height:90px; }
    .actions { display:flex; flex-wrap:wrap; gap:10px; margin:18px 0; } .secondary { background:#fff!important; color:var(--green)!important; border:1px solid var(--green)!important; }
  </style>
</head>
<body><main><section class="card">
  <h1>BigShot Business Data Import</h1>
  <p>The existing Excel macro import workflow remains available through its established API endpoints.</p>
  <p>Daily vegetable production is entered directly in <strong>Veggies Production Basic</strong>, not through Excel.</p>
  <div class="actions"><a class="button secondary" href="/business-os/veggies-production">Open Veggies Production Basic</a></div>
  <!-- Optional legacy utilities below are intentionally not part of the normal production workflow. -->
  <div hidden>
  <label>Import type
    <select id="importType">
      <option value="veggies_production">Veggies Production</option>
      <option value="legacy">Existing Business Import (Excel macro workflow)</option>
    </select>
  </label>
  <div class="actions"><a class="button secondary" href="/template/veggies-production">Download Veggies Production Template</a></div>
  <form id="uploadForm">
    <label>Completed workbook<input id="workbook" name="workbook" type="file" accept=".xlsx" required></label>
    <button id="previewButton" type="submit">Preview / Dry Run</button>
  </form>
  <div class="actions">
    <button id="importButton" type="button" disabled>Confirm Import</button>
    <a class="button secondary" id="errorsButton" hidden>Download Rejected Rows</a>
  </div>
  <div id="result" role="status">Select a workbook to preview.</div></div>
</section></main>
<script>
let previewId = null;
const result = document.getElementById('result');
document.getElementById('uploadForm').addEventListener('submit', async (event) => {
  event.preventDefault(); previewId = null; document.getElementById('importButton').disabled = true;
  const response = await fetch('/veggies-production/preview', { method:'POST', body:new FormData(event.target) });
  const payload = await response.json();
  if (!response.ok) { result.textContent = payload.error || 'Preview failed.'; return; }
  previewId = payload.preview_id;
  result.textContent = `Source rows: ${payload.total_source_rows}\nAccepted rows: ${payload.accepted_rows}\nRejected rows: ${payload.rejected_rows}\nNormalized items: ${payload.normalized_items}\nDuplicate rows: ${payload.duplicate_rows.length}`;
  document.getElementById('importButton').disabled = payload.accepted_rows === 0;
  const errors = document.getElementById('errorsButton');
  errors.hidden = payload.rejected_rows === 0; errors.href = `/veggies-production/rejections/${previewId}`;
});
document.getElementById('importButton').addEventListener('click', async () => {
  if (!previewId) return;
  const button = document.getElementById('importButton'); button.disabled = true;
  const response = await fetch('/veggies-production/import', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({preview_id:previewId}) });
  const payload = await response.json(); result.textContent = JSON.stringify(payload, null, 2);
});
</script></body></html>"""


@app.get("/")
def import_page():
    return Response(IMPORT_PAGE, content_type="text/html; charset=utf-8")


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.get("/template/veggies-production")
def veggies_template():
    if not VEGGIES_TEMPLATE.exists():
        return jsonify({"ok": False, "error": "Veggies Production template is not generated."}), 404
    return send_file(
        VEGGIES_TEMPLATE,
        as_attachment=True,
        download_name="BigShot_Veggies_Production_Template.xlsx",
    )


@app.post("/veggies-production/preview")
def preview_veggies_production():
    upload = request.files.get("workbook")
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "error": "An .xlsx workbook is required."}), 400
    if not upload.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "error": "Only .xlsx workbooks are supported."}), 400
    try:
        preview = parse_veggies_workbook(upload.stream, load_crop_definitions())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    preview.filename = upload.filename
    preview_id = secrets.token_urlsafe(24)
    _VEGGIES_PREVIEWS[preview_id] = preview
    return jsonify({"ok": True, "preview_id": preview_id, **preview.as_dict(include_rows=True)})


@app.post("/veggies-production/import")
def import_veggies_production():
    payload = request.get_json(silent=True) or {}
    preview_id = str(payload.get("preview_id") or "")
    preview = _VEGGIES_PREVIEWS.get(preview_id)
    if preview is None:
        return jsonify({"ok": False, "error": "Preview expired or does not exist."}), 404
    try:
        result = import_veggies_preview(preview, imported_by=request.remote_addr or "business-import")
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    _VEGGIES_PREVIEWS.pop(preview_id, None)
    return jsonify(result)


@app.get("/veggies-production/rejections/<preview_id>")
def veggies_rejections(preview_id):
    preview = _VEGGIES_PREVIEWS.get(preview_id)
    if preview is None:
        return jsonify({"ok": False, "error": "Preview expired or does not exist."}), 404
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Row", "Column", "Error"])
    for error in preview.errors:
        writer.writerow([error.row_number, error.column, error.message])
    return Response(
        output.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=Veggies_Production_Rejected_Rows.csv"},
    )


@app.post("/import")
def import_rows():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "JSON body is required"}), 400

    try:
        results = import_excel_payload(payload)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    has_errors = _has_import_errors(results)
    return jsonify({
        "ok": not has_errors,
        "results": results,
    }), 207 if has_errors else 200


@app.post("/import-vba")
def import_rows_for_vba():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return "ERROR|JSON body is required\n", 400, {"Content-Type": "text/plain"}

    try:
        results = import_excel_payload(payload)
    except Exception as exc:
        return f"ERROR|{_line_value(str(exc))}\n", 500, {"Content-Type": "text/plain"}

    lines = ["OK"]
    for table_key, result in results.items():
        if table_key.startswith("_"):
            continue
        for row in result["inserted"]:
            lines.append(
                "|".join([
                    result["table"],
                    str(row.get("row_number") or ""),
                    "INSERTED",
                    str(row.get("id") or ""),
                    "",
                ])
            )
        for row in result["errors"]:
            lines.append(
                "|".join([
                    result["table"],
                    str(row.get("row_number") or ""),
                    "ERROR",
                    "",
                    _line_value(row.get("error") or ""),
                ])
            )

    has_errors = _has_import_errors(results)
    return "\n".join(lines) + "\n", 207 if has_errors else 200, {"Content-Type": "text/plain"}


def _has_import_errors(results):
    return any(
        result.get("errors")
        for table_key, result in results.items()
        if not table_key.startswith("_")
    )


def _line_value(value):
    return str(value).replace("|", "/").replace("\r", " ").replace("\n", " ")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055)
