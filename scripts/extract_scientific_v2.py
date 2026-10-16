"""Explicit opt-in isolated scientific extraction; never mutates a corpus catalog."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evidence.v2.runner import extract
from src.evidence.v2.runtime import Config

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--paper-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--enable", action="store_true")
    p.add_argument("--local-model-config", type=Path)
    p.add_argument("--tokenizer-path", type=Path)
    a=p.parse_args()
    model=None
    if a.local_model_config:
        import yaml
        model=yaml.safe_load(a.local_model_config.read_text(encoding="utf-8"))["llm"]
        if a.tokenizer_path:model["tokenizer_path"]=str(a.tokenizer_path)
    result=extract(a.source,a.paper_id,a.output,
        config=Config(enabled=a.enable,local_model_enabled=bool(model)),model=model)
    print(json.dumps({"state":result.get("state"),"facts":len(result["facts"]),
                      "coverage":result.get("coverage")}))
if __name__=="__main__":main()
