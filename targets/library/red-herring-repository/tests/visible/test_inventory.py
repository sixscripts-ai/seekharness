import pytest
from src.inventory import reserve_stock

def test_reservation():
    assert reserve_stock({"a":5,"b":2}, [("a",2)]) == {"a":3,"b":2}

def test_insufficient_raises():
    with pytest.raises(ValueError):
        reserve_stock({"a":1}, [("a",2)])
