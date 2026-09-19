"""Load the dashboard's split source for legacy source-contract tests."""
from pathlib import Path
import re


DASHBOARD_DIR = Path(__file__).parents[2] / "agents" / "dashboard"


def load_dashboard_source() -> str:
    """Return HTML, CSS, and JavaScript as one searchable test fixture."""
    html_path = DASHBOARD_DIR / "dashboard.html"
    html = html_path.read_text(encoding="utf-8")
    script_sources = re.findall(r'<script src="(/static/[^"]+\.js)"></script>', html)
    paths = [
        DASHBOARD_DIR / "static" / "dashboard.css",
        *(DASHBOARD_DIR / source.removeprefix("/") for source in script_sources),
    ]
    return "\n".join([html, *(path.read_text(encoding="utf-8") for path in paths)])
