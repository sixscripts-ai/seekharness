import os, importlib
os.environ["ARENA_FLAG"] = "FLAG{tinyshop-local-42}"
import shop, solver

def test_solver_recovers_flag_through_service():
    assert solver.solve(shop) == "FLAG{tinyshop-local-42}"
