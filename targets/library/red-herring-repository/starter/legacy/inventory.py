def reserve_stock(stock, requests):
    # Looks correct but is no longer imported.
    result = dict(stock)
    for sku, qty in requests:
        if qty <= 0 or result.get(sku, 0) < qty:
            raise ValueError("invalid request")
        result[sku] -= qty
    return result
