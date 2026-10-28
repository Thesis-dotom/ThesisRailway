
from pathlib import Path
import ast

root = Path(__file__).resolve().parent
app_source = (root / "app.py").read_text(encoding="utf-8")

for path in root.glob("*.py"):
    ast.parse(path.read_text(encoding="utf-8"))

required = [
    "templates/index.html",
    "templates/how_to_invest.html",
    "templates/top_opportunities.html",
    "templates/methodology.html",
    "templates/disclosures.html",
    "static/styles.css",
    "static/favicon.svg",
    "requirements.txt",
    "Procfile",
    "Dockerfile",
    "templates/discover.html",
    "templates/suggest_company.html",
    "templates/admin_inbox.html",
    ".github/workflows/weekly-refresh.yml",
]
missing = [item for item in required if not (root / item).exists()]
if missing:
    raise SystemExit(f"Missing files: {missing}")

print("Structure and Python syntax checks passed.")
