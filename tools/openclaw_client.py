import requests
from config import OLLAMA_URL, AI_MODEL


def ask_ai(prompt, model=None, timeout=60):

    payload = {
        "model": model or AI_MODEL,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=timeout,
    )

    data = response.json()

    return data["response"]
