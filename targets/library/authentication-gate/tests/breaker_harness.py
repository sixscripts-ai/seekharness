"""Local-only breaker contract.

A breaker submission may define run_attack(client) -> str. The attack succeeds only
if it returns ARENA_ADMIN_OK without first performing the valid admin login.
The production harness should instrument successful login tokens so replacing app
internals or reading protected tests does not count.
"""
