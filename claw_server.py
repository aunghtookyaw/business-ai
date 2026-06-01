from flask import Flask, request, jsonify
from tool_registry import TOOLS

app = Flask(__name__)

@app.route("/tool", methods=["POST"])
def run_tool():

    data = request.json

    tool_name = data.get("tool")
    args = data.get("args", [])

    if tool_name not in TOOLS:
        return jsonify({
            "success": False,
            "error": "Tool not found"
        })

    try:
        result = TOOLS[tool_name](*args)

        return jsonify({
            "success": True,
            "result": str(result)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
