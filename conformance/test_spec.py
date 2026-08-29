"""pytest shim: `pytest conformance/` discovers one test per SPEC clause.
Each clause is a real assertion, so a red test means the implementation is
not Safety-Protocol-compatible for that clause."""
import pytest
from conformance import CLAUSES


@pytest.mark.parametrize("fn", CLAUSES, ids=[f.__name__ for f in CLAUSES])
def test_clause(fn):
    clause, passed, detail = fn()
    assert passed, f"{clause} FAILED: {detail}"
