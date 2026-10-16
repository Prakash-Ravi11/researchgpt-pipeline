"""Owned blocking parser process: no shell, model or document instructions."""
import argparse
from pathlib import Path
from .inventory import inventory_pdf
from src.evidence.monitor import atomic_json_write

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document=inventory_pdf(args.source,args.paper_id)
    atomic_json_write(args.output,document)
    from .resources import process_memory
    atomic_json_write(args.output.parent/"parser_resources.json",process_memory())

if __name__ == "__main__":
    main()
