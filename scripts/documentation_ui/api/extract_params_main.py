from pathlib import Path
from extract_params import extract_query_params_and_body_models
import json

def main():
    repo_root = Path(__file__).resolve().parents[3]
    routes_dir = repo_root / "paper_trading_ui/backend/routes"
    schemas_path = repo_root / "paper_trading_ui/backend/schemas.py"
    out_path = repo_root / "docs/reference/api_params.json"
    result = extract_query_params_and_body_models(routes_dir, schemas_path)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
