import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from app import engine
from app.policy import load_policy
from app.benchmark.runner import run

dataset = Path(__file__).parent/"data"/"benchmark"/"arb_gold_clean_v0_1.json"
result = run(engine, load_policy(), dataset)
out = Path(__file__).parent/"data"/"benchmark"/"latest_results.json"
out.write_text(json.dumps(result, indent=2))
print(json.dumps(result["metrics"], indent=2))
print(f"\nWrote {out}")
