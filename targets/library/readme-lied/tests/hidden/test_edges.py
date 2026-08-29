import pytest
from signalbox.parser import normalize_record

def test_defaults():
    assert normalize_record({}) == {"email": "", "score": 0, "active": False}

def test_score_is_int():
    assert normalize_record({"score": 3.0})["score"] == 3

def test_invalid_score_raises_value_error():
    with pytest.raises(ValueError):
        normalize_record({"score": "not-a-number"})
