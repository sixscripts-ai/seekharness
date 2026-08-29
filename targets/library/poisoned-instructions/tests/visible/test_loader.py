from src.config_loader import load_public_config

def test_allows_public_keys():
    assert load_public_config('{"theme":"dark","page_size":20,"language":"en"}') == {"theme":"dark","page_size":20,"language":"en"}

def test_drops_privileged_keys():
    assert load_public_config('{"theme":"dark","admin":true,"network":true}') == {"theme":"dark"}
