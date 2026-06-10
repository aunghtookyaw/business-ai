import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, jsonify, request

from tools.excel_importer import import_excel_payload


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"ok": True})


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
