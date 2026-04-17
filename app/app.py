"""Flask demo app: run investigation from a web form and display results."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv
load_dotenv(dotenv_path=ROOT / ".env")
import os as _os
print(f"[app] GROQ_API_KEY loaded: {bool(_os.environ.get('GROQ_API_KEY'))}", flush=True)

from flask import Flask, render_template, request

from app.pipeline import run_investigation, get_registered_entities, QUERY_TEMPLATES

app = Flask(__name__, template_folder=Path(__file__).resolve().parent / "templates")


@app.route("/", methods=["GET", "POST"])
def index():
    entities = get_registered_entities()
    templates = QUERY_TEMPLATES
    if request.method == "GET":
        return render_template("index.html", entities=entities, templates=templates)
    query = (request.form.get("query") or "").strip()
    if not query:
        return render_template("index.html", error="Please enter an investigation query.", entities=entities, templates=templates)
    data_root = ROOT / "data"
    result = run_investigation(query, data_root=data_root)
    # Extract body fragment for embedding (report_html is full document)
    if result.get("report_html"):
        html = result["report_html"]
        if "<body>" in html and "</body>" in html:
            start = html.index("<body>") + len("<body>")
            end = html.index("</body>")
            result["report_body"] = html[start:end].strip()
        else:
            result["report_body"] = html
    else:
        result["report_body"] = ""
    return render_template("results.html", result=result)


def main():
    app.run(host="0.0.0.0", port=5001, debug=True)


if __name__ == "__main__":
    main()
