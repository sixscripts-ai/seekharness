def reserve_stock(stock: dict[str,int], requests: list[tuple[str,int]]) -> dict[str,int]:
    """Return new stock after all reservations; reject invalid batches atomically."""
    result = dict(stock)
    for sku, qty in requests:
        if sku not in result:
            continue
        if result[sku] < qty:
            return result
        result[sku] -= qty
    return result
