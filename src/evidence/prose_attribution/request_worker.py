"""Single-request transport worker, killed by the host at its hard deadline.

This is a timeout boundary, not an iterative agent. It reuses ResearchIQ's
invocation/parsing/trace and preserves streamed partial responses incrementally.
"""
import argparse
import json
import time
from pathlib import Path

import requests

from src.evidence.monitor import ExtractionTrace
from src.summarization.summarize import call_ollama_json


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    directory = args.response.parent
    trace = ExtractionTrace(directory / "trace", {"protocol_version": request["prompt_version"],
                                                "document_id": request["document_id"], "attempt": request["attempt"]})
    original = requests.sessions.Session.send

    def observed_send(session, prepared, **kwargs):
        if prepared.url != request["base_url"].rstrip("/") + "/api/chat":
            raise RuntimeError("Only the configured local chat endpoint is allowed")
        write(directory / "actual_request.json", {"url": prepared.url, "payload": json.loads(prepared.body),
                                                  "timeout": kwargs.get("timeout"), "stream": kwargs.get("stream")})
        response = original(session, prepared, **kwargs)
        lines = response.iter_lines

        def observed_lines(*line_args, **line_kwargs):
            # The invocation's default 512-byte line buffer can hold a complete
            # early chunk while the server stalls. Read bytes promptly so each
            # completed NDJSON event is durable before a hard cancellation.
            line_kwargs.setdefault("chunk_size", 1)
            with (directory / "raw_response.ndjson").open("w", encoding="utf-8") as stream:
                for line in lines(*line_args, **line_kwargs):
                    decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                    stream.write(decoded + "\n")
                    stream.flush()
                    yield line
        response.iter_lines = observed_lines
        return response

    requests.sessions.Session.send = observed_send
    started = time.perf_counter()
    try:
        meta = {}
        settings = request["settings"]
        parsed = call_ollama_json(request["base_url"], request["model"], request["system_prompt"],
                                 request["user_content"], temperature=settings["temperature"], seed=settings["seed"],
                                 num_ctx=settings["num_ctx"], num_predict=settings["num_predict"], max_retries=0,
                                 timeout=min(settings["request_seconds"], 30), deadline_seconds=settings["request_seconds"],
                                 response_schema=request["response_schema"], meta_out=meta, trace=trace)
        trace.finish("completed" if isinstance(parsed, dict) and meta.get("done_reason") == "stop" else "failed")
        write(args.response, {"parsed": parsed, "metadata": meta, "elapsed_s": time.perf_counter() - started,
                              "trace_errors": trace.errors})
    finally:
        requests.sessions.Session.send = original


if __name__ == "__main__":
    main()
