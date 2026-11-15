"""Explicit opt-in local Ollama helper; sends only minimal metadata."""

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def suggest(
    metadata,
    endpoint="http://127.0.0.1:11434/api/generate",
    model="llama3.2",
    enabled=False,
    timeout=5,
):
    if not enabled:
        raise ValueError("Local suggestions are disabled until explicitly enabled.")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Ollama endpoint must be loopback HTTP.")
    safe = [
        {
            "type": str(row.get("category", "unknown"))[:40],
            "size": int(row.get("size", 0)),
            "reason": str(row.get("reason", "review"))[:160],
        }
        for row in metadata[:100]
    ]
    prompt = (
        "Give brief organization explanations only for this metadata. Do not propose actions. "
        + json.dumps(safe)
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    request = Request(
        endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read(100000))
    return str(result.get("response", ""))[:1000]
