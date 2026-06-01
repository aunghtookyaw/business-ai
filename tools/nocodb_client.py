import requests
from config import (
    NOCODB_URL,
    NOCODB_API_TOKEN,
    TABLE_ID
)

headers = {
    "xc-token": NOCODB_API_TOKEN
}

def get_transactions():

    url = f"{NOCODB_URL}/api/v2/tables/{TABLE_ID}/records"

    response = requests.get(
        url,
        headers=headers
    )

    data = response.json()


    return data["list"]


if __name__ == "__main__":

    records = get_transactions()
