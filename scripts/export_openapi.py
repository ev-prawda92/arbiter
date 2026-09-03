import json
from pathlib import Path
from backend.app.main import app

out = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2))
print(out)
