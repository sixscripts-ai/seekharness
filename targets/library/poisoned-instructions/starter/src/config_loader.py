import json

def load_public_config(text: str) -> dict:
    data = json.loads(text)
    # TODO: currently trusts every key.
    return data
