def reserve_stock(stock: dict[str,int], requests: list[tuple[str,int]]) -> dict[str,int]:
    result = dict(stock)
    for sku, qty in requests:
        if sku not in result or isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            raise ValueError("invalid request")
        if result[sku] < qty:
            raise ValueError("insufficient stock")
        result[sku] -= qty
    return result
