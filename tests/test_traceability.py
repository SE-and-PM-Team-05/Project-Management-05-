"""Keeps the test suite traceable to the SRS (SCRUM-55, see "Test names and SRS requirement IDs" in README.md)."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
ID_PATTERN = re.compile(r"REQ-[A-Z]+-\d{3}")


def srs_requirement_ids():
    """Every requirement ID defined in a table row of docs/SRS.md, e.g. `| REQ-SEC-004 | ...`."""
    srs = (ROOT / "docs" / "SRS.md").read_text(encoding="utf-8")
    return set(re.findall(r"^\| (REQ-[A-Z]+-\d{3}) \|", srs, flags=re.MULTILINE))


def collect_test_functions():
    """(file name, function name, docstring) of every test function in tests/."""
    found = []
    for path in sorted(TESTS.glob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                found.append((path.name, node.name, ast.get_docstring(node) or ""))
    return found


def test_the_srs_defines_requirement_ids():
    """REQ-MAINT-002: the ID list below is only useful if the SRS table rows are really found."""
    assert len(srs_requirement_ids()) > 100


def test_every_test_names_the_requirement_it_verifies():
    """REQ-MAINT-002: every test function names at least one requirement ID in its docstring."""
    without_id = [f"{file}::{name}" for file, name, doc in collect_test_functions() if not ID_PATTERN.search(doc)]
    assert not without_id, "Name the SRS requirement ID(s) in the docstring of: " + ", ".join(without_id)


def test_every_named_requirement_exists_in_the_srs():
    """REQ-MAINT-002: a mistyped ID would hide a test from the search for the real ID."""
    known = srs_requirement_ids()
    unknown = sorted(
        {i for _, _, doc in collect_test_functions() for i in ID_PATTERN.findall(doc)} - known,
    )
    assert not unknown, "Not defined in docs/SRS.md: " + ", ".join(unknown)
