import pytest
import tokens

def test_round_trip_once():
    t = tokens.issue("alice", 100)
    assert tokens.verify(t, 110) == "alice"
    with pytest.raises(ValueError):
        tokens.verify(t, 111)
