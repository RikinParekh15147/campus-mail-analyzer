"""Bounded JSONL reads shared by corpus audit, migration and import staging."""

import hashlib
import json
from pathlib import Path

from .validation import _reject_constant, _unique_keys


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jsonl_records(path, max_line_bytes=16 * 1024 * 1024):
    """Yield (line, object, line hash, error code); never expose parse exception text."""
    if max_line_bytes < 1:
        raise ValueError("Line limit must be positive")
    with Path(path).open("rb") as stream:
        line = 0
        while chunk := stream.readline(max_line_bytes + 1):
            line += 1
            digest = hashlib.sha256(chunk)
            if len(chunk) > max_line_bytes:
                while not chunk.endswith(b"\n"):
                    chunk = stream.readline(max_line_bytes + 1)
                    if not chunk:
                        break
                    digest.update(chunk)
                yield line, None, digest.hexdigest(), "line_too_large"
                continue
            try:
                value = json.loads(
                    chunk.decode("utf-8"),
                    object_pairs_hook=_unique_keys,
                    parse_constant=_reject_constant,
                )
                if not isinstance(value, dict):
                    raise ValueError("Expected an object")
            except (ValueError, UnicodeDecodeError, RecursionError):
                yield line, None, digest.hexdigest(), "invalid_json_object"
                continue
            yield line, value, digest.hexdigest(), None
