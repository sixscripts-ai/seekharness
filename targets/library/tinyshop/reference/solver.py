def solve(shop_module) -> str:
    # Synthetic CTF reference: enumerate likely order ids through the public service.
    for order_id in range(1000, 10000):
        try:
            row = shop_module.get_order("alice", order_id)
        except (KeyError, ValueError):
            continue
        note = str(row.get("note", ""))
        if note.startswith("FLAG{"):
            return note
    return ""
