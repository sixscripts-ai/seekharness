import json
ALLOWED = {"theme", "page_size", "language"}

def load_public_config(text: str) -> dict:
    data = json.loads(text)
    out = {k:v for k,v in data.items() if k in ALLOWED}
    if "page_size" in out:
        size = out["page_size"]
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 100:
            raise ValueError("page_size must be an integer from 1 to 100")
    return out
