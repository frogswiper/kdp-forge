"""Ollama HTTP client."""
import json
import os
import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:31b-cloud")


async def list_models() -> list[str]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{OLLAMA_URL}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]


async def chat_json(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    schema_hint: dict | None = None,
    temperature: float = 0.6,
    timeout: float = 180.0,
) -> dict:
    """Ask Ollama for a JSON response. Uses format='json' to enforce a JSON object.

    schema_hint is rendered into the user prompt so the model knows the shape.
    """
    if schema_hint is not None:
        user = (
            user
            + "\n\nReturn ONLY a JSON object matching this shape (no prose, no markdown):\n"
            + json.dumps(schema_hint, indent=2)
        )
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        body = r.json()
    raw = body.get("message", {}).get("content", "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Some models wrap output in code fences; try to recover.
        s = raw.strip()
        if s.startswith("```"):
            s = s.strip("`")
            if s.startswith("json"):
                s = s[4:]
        return json.loads(s)
