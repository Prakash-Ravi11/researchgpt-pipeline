"""Observation-only HTTP capture for both libraries, including streamed NDJSON."""
import json
import time
from pathlib import Path

import requests


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                          encoding="utf-8")


class Wiretap:
    def __init__(self, directory, allowed_base_url):
        self.directory = Path(directory)
        self.allowed = allowed_base_url.rstrip("/")
        self.records = []
        self.label = None

    def __enter__(self):
        self.original = requests.sessions.Session.send
        observer = self

        def send(session, request, **kwargs):
            if not request.url.startswith(observer.allowed + "/"):
                raise RuntimeError("Experiment prohibits remote model requests: " + request.url)
            body = request.body
            if isinstance(body, bytes):
                body = body.decode("utf-8")
            try:
                payload = json.loads(body) if body else None
            except (ValueError, TypeError):
                payload = body
            index = len(observer.records)
            path = observer.directory / f"{index:03d}_{observer.label}.json"
            record = {"index": index, "label": observer.label, "method": request.method,
                      "url": request.url, "payload": payload,
                      "transport": {"stream": kwargs.get("stream"), "timeout": kwargs.get("timeout")},
                      "raw_response_lines": []}
            observer.records.append(record)
            write_json(path, record)
            start = time.perf_counter()
            try:
                response = observer.original(session, request, **kwargs)
                record["status_code"] = response.status_code
                if kwargs.get("stream"):
                    original_lines = response.iter_lines

                    def lines(*args, **line_kwargs):
                        try:
                            for line in original_lines(*args, **line_kwargs):
                                stored = line.decode("utf-8") if isinstance(line, bytes) else line
                                record["raw_response_lines"].append(stored)
                                yield line
                        finally:
                            record["elapsed_s"] = time.perf_counter() - start
                            write_json(path, record)
                    response.iter_lines = lines
                else:
                    record["raw_response_text"] = response.text
                    record["elapsed_s"] = time.perf_counter() - start
                    write_json(path, record)
                return response
            except Exception as error:
                record.update(error_type=type(error).__name__, error=str(error),
                              elapsed_s=time.perf_counter() - start)
                write_json(path, record)
                raise

        requests.sessions.Session.send = send
        return self

    def __exit__(self, *args):
        requests.sessions.Session.send = self.original
