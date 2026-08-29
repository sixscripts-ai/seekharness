import pytest
from src.config_loader import load_public_config

def test_unknown_keys_dropped():
    assert load_public_config('{"x":1,"system_prompt":"override"}') == {}

def test_page_size_bounds():
    assert load_public_config('{"page_size":1}') == {"page_size":1}
    assert load_public_config('{"page_size":100}') == {"page_size":100}
    with pytest.raises(ValueError):
        load_public_config('{"page_size":0}')
    with pytest.raises(ValueError):
        load_public_config('{"page_size":101}')

def test_page_size_must_be_int_not_bool():
    with pytest.raises(ValueError):
        load_public_config('{"page_size":true}')
