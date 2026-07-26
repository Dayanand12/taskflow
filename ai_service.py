"""Centralized AI service.

This is the only place in the app that talks to Ollama. Any AI feature
(flashcard generation, summaries, quizzes, explanations, etc.) should call
through the functions here instead of hitting Ollama directly, so there is
a single point for connection handling, timeouts, and error formatting.
"""

import requests

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:8b"
CONNECT_TIMEOUT = 5
GENERATE_TIMEOUT = 120


def _base(base_url):
    return (base_url or DEFAULT_BASE_URL).rstrip("/")


def test_connection(base_url):
    """Check whether Ollama is reachable and list installed models.

    Returns (ok: bool, data: dict). On success data = {"models": [...]}.
    On failure data = {"error": "human-readable message"}.
    """
    try:
        r = requests.get(f"{_base(base_url)}/api/tags", timeout=CONNECT_TIMEOUT)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return True, {"models": models}
    except requests.exceptions.ConnectTimeout:
        return False, {"error": "Connection timed out. Is Ollama running?"}
    except requests.exceptions.ConnectionError:
        return False, {"error": "Could not connect. Is Ollama running at this address?"}
    except requests.exceptions.Timeout:
        return False, {"error": "Request timed out."}
    except requests.exceptions.HTTPError as e:
        return False, {"error": f"Ollama returned an error: {e}"}
    except Exception as e:
        return False, {"error": str(e)}


def generate(prompt, base_url, model, system=None, fmt=None, timeout=GENERATE_TIMEOUT):
    """Generic single-shot text generation. Returns (ok: bool, text_or_error: str)."""
    payload = {"model": model, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system
    if fmt:
        payload["format"] = fmt
    try:
        r = requests.post(f"{_base(base_url)}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        return True, r.json().get("response", "")
    except requests.exceptions.ConnectTimeout:
        return False, "Connection timed out. Is Ollama running?"
    except requests.exceptions.ConnectionError:
        return False, "Could not connect to Ollama."
    except requests.exceptions.Timeout:
        return False, "Ollama request timed out (the model may be slow to respond)."
    except requests.exceptions.HTTPError as e:
        return False, f"Ollama returned an error: {e}"
    except Exception as e:
        return False, str(e)
