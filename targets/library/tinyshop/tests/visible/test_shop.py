import shop, solver

def test_normal_listing_is_scoped():
    assert shop.list_orders("alice") == [1001]

def test_solver_returns_a_flag_in_dev_mode():
    assert solver.solve(shop).startswith("FLAG{")
