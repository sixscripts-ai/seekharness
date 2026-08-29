# TinyShop

This is a synthetic, local-only CTF. `shop.py` models a tiny web service. Write `solver.py` exposing `solve(shop_module) -> str` that recovers the `FLAG{...}` value by using the service's public functions. The production harness provides the flag at runtime; direct protected-file access is out of scope.
