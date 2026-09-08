import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.main import app

out = ROOT / "docs" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2))
print(out)
