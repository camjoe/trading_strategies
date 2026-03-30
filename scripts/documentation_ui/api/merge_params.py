import json
from pathlib import Path

def merge_params_into_api_json(api_json_path, params_json_path):
    api_data = json.loads(Path(api_json_path).read_text(encoding="utf-8"))
    params_data = json.loads(Path(params_json_path).read_text(encoding="utf-8"))
    for endpoint in api_data["endpoints"]:
        key = f"{endpoint['method']} {endpoint['path']}"
        param_info = params_data.get(key)
        if param_info:
            endpoint["query_params"] = param_info.get("query_params", [])
            # If body_model is None, add placeholder for POST endpoints
            if endpoint["method"] == "POST":
                endpoint["body_model"] = param_info.get("body_model") or "not yet extracted"
            else:
                endpoint["body_model"] = None
        else:
            endpoint["query_params"] = []
            endpoint["body_model"] = "not yet extracted" if endpoint["method"] == "POST" else None
    Path(api_json_path).write_text(json.dumps(api_data, indent=2) + "\n", encoding="utf-8")
    print(f"Updated: {api_json_path}")

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    merge_params_into_api_json(
        repo_root / "docs/reference/api.json",
        repo_root / "docs/reference/api_params.json"
    )
