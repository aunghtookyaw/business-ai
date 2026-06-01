import os
import sys

import requests
from requests import RequestException

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import config
except ImportError:
    config = None


def setting(name, default=None, aliases=None):
    for candidate in [name] + list(aliases or []):
        value = os.getenv(candidate)
        if value not in (None, ""):
            return value

    if config is not None:
        for candidate in [name] + list(aliases or []):
            value = getattr(config, candidate, None)
            if value not in (None, ""):
                return value

    return default


def telegram_get(base_url, method, **params):
    try:
        response = requests.get(
            f"{base_url}/{method}",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except RequestException as exc:
        raise RuntimeError(f"Telegram API request failed for {method}: {exc.__class__.__name__}") from exc


def main():
    token = setting(
        "FAMILY_TELEGRAM_BOT_TOKEN",
        aliases=["BIGSHOT_GUY_BOT_TOKEN"],
    )
    chat_id = setting("FAMILY_ALLOWED_CHAT_ID", "-1003850232296")

    if not token:
        print("Family bot token: MISSING")
        print("Add FAMILY_TELEGRAM_BOT_TOKEN or BIGSHOT_GUY_BOT_TOKEN to config.py.")
        return 1

    base_url = f"https://api.telegram.org/bot{token}"

    me = telegram_get(base_url, "getMe")
    if not me.get("ok"):
        print(f"getMe failed: {me.get('description')}")
        return 1

    bot = me["result"]
    print("Family bot token: SET")
    print(f"Bot username: @{bot.get('username')}")
    print(f"Bot id: {bot.get('id')}")

    member = telegram_get(
        base_url,
        "getChatMember",
        chat_id=chat_id,
        user_id=bot["id"],
    )
    if member.get("ok"):
        print(f"Group membership in {chat_id}: {member['result'].get('status')}")
        return 0

    print(f"Group membership check failed: {member.get('description')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
