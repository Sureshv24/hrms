import inspect
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.core.permissions import require_roles
from app.routers.compensation import router


def collect_roles(dependant):
    roles = set()

    call = dependant.call
    if call is not None and getattr(call, "__name__", "") == "role_checker":
        values = inspect.getclosurevars(call).nonlocals
        roles.update(values.get("allowed_roles", ()))

    for child in dependant.dependencies:
        roles.update(collect_roles(child))

    return roles


print("===== COMPENSATION ENDPOINT ACCESS RULES =====")

for route in router.routes:
    if not isinstance(route, APIRoute):
        continue

    methods = ",".join(sorted(route.methods or []))
    roles = sorted(collect_roles(route.dependant))

    print(f"{methods:8} {route.path:55} roles={roles}")

# Directly test the shared authorization helper.
checker = require_roles("Admin", "HR")

for role in ("Admin", "HR"):
    result = checker(SimpleNamespace(role=role))
    assert result.role == role
    print(f"PASS: {role} access allowed by helper")

try:
    checker(SimpleNamespace(role="Employee"))
except HTTPException as exc:
    assert exc.status_code == 403
    print("PASS: Employee access denied with HTTP 403")
else:
    raise AssertionError("Employee was not rejected by role checker")

try:
    checker(SimpleNamespace(role="Support"))
except HTTPException as exc:
    assert exc.status_code == 403
    print("PASS: Support access denied with HTTP 403")
else:
    raise AssertionError("Support was not rejected by role checker")

# Confirm all compensation endpoints have a role guard.
for route in router.routes:
    if isinstance(route, APIRoute):
        assert collect_roles(route.dependant), (
            f"Missing discoverable role guard: {route.path}"
        )

print("PASS: All compensation routes have discoverable role guards.")
