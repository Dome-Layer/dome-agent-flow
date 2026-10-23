"""House style: no em or en dashes in the backend source.

Rule messages are shown to the approver and the governance summary appears
in the Governance Dashboard, so neither may contain the em dash (U+2014) or
the en dash (U+2013). The shim writes no model text of its own: P2 and P3
clean theirs before it arrives here.
"""

from pathlib import Path

EM = "\N{EM DASH}"
EN = "\N{EN DASH}"

BACKEND = Path(__file__).resolve().parents[1]
SCANNED_FILES = [*sorted((BACKEND / "app").rglob("*.py")), BACKEND / "policy.yaml"]


def test_no_dashes_in_backend_source() -> None:
    offenders = [
        f"{path.relative_to(BACKEND)}:{number}"
        for path in SCANNED_FILES
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if EM in line or EN in line
    ]
    assert not offenders, "Em or en dash found (house style):\n" + "\n".join(offenders)
