import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import config
except ImportError:
    config = None

from tools.openclaw_client import ask_ai


def setting(name, default=None):
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    if config is not None:
        value = getattr(config, name, None)
        if value not in (None, ""):
            return value
    return default


def main():
    url = setting("OLLAMA_URL", "http://localhost:11434/api/generate")
    model = setting("FAMILY_AI_MODEL", setting("AI_MODEL", "qwen3:latest"))

    print(f"Ollama URL: {url}")
    print(f"Model: {model}")

    start_time = time.time()
    answer = ask_ai("Reply with OK only.", model=model, timeout=60).strip()
    elapsed = time.time() - start_time

    print(f"Local AI response: {answer}")
    print(f"Elapsed: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
