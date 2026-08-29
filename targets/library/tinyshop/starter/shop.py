import os

ORDERS = {
    1001: {"owner":"alice", "item":"mug", "note":"thanks"},
    1002: {"owner":"bob", "item":"shirt", "note":"gift"},
    9001: {"owner":"admin", "item":"internal", "note":None},
}

def get_order(current_user: str, order_id: int) -> dict:
    # Intentionally vulnerable IDOR: owner is not checked.
    order = dict(ORDERS[order_id])
    if order_id == 9001:
        order["note"] = os.environ.get("ARENA_FLAG", "FLAG{development-placeholder}")
    return order

def list_orders(current_user: str) -> list[int]:
    return [oid for oid, row in ORDERS.items() if row["owner"] == current_user]
