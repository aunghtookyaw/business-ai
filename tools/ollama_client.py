import requests
from config import OLLAMA_URL, AI_MODEL


def ask_ai(prompt, model=None, timeout=60):
    selected_model = model or AI_MODEL

    payload = {
        "model": selected_model,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    if "response" not in data:
        raise RuntimeError(f"Ollama returned no response for model {selected_model}.")

    return data["response"]
