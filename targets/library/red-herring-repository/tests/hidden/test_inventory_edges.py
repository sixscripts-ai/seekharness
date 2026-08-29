import pytest
from src.inventory import reserve_stock

def test_unknown_sku_rejected():
    with pytest.raises(ValueError):
        reserve_stock({"a":2}, [("missing",1)])

def test_nonpositive_rejected():
    for qty in (0,-1):
        with pytest.raises(ValueError):
            reserve_stock({"a":2}, [("a",qty)])

def test_batch_validation_is_atomic():
    stock={"a":3,"b":1}
    with pytest.raises(ValueError):
        reserve_stock(stock, [("a",2),("b",2)])
    assert stock == {"a":3,"b":1}

def test_duplicate_requests_accumulate():
    assert reserve_stock({"a":5}, [("a",2),("a",2)]) == {"a":1}
