"""Migrations only expand (R2-19): the previous release's code must run on the
newer schema, because a rollback redeploys old images on the current database
and never runs old migrations. Dropping or renaming a table or column in
`upgrade()` is a contract step: allowed only in a migration that says which
release stopped using it, `# contract: <release>`, shipped at least one
release after that code went out (docs/runbook.md "Releasing and rolling back").
"""

from __future__ import annotations

import ast
from pathlib import Path

VERSIONS = sorted((Path(__file__).parents[3] / "services").glob("*/*/migrations/versions/*.py"))
CONTRACT = {"drop_column", "drop_table", "rename_table"}


def contract_steps(source: str) -> list[str]:
    """Calls in upgrade() that break the previous release's code."""
    found = []
    for fn in ast.parse(source).body:
        if isinstance(fn, ast.FunctionDef) and fn.name == "upgrade":
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                    renames = name == "alter_column" and any(k.arg == "new_column_name" for k in node.keywords)
                    if name in CONTRACT or renames:
                        found.append(f"{name} (line {node.lineno})")
    return found


def test_the_rule_catches_contract_steps():
    drop = "def upgrade():\n    op.drop_column('t', 'c')\n\ndef downgrade():\n    op.drop_table('t')\n"
    rename = (
        "def upgrade():\n    with op.batch_alter_table('t') as b:\n        b.alter_column('a', new_column_name='b')\n"
    )
    assert contract_steps(drop) == ["drop_column (line 2)"], "downgrade() may drop, upgrade() may not"
    assert contract_steps(rename) == ["alter_column (line 3)"]
    assert contract_steps("def upgrade():\n    op.add_column('t', sa.Column('c'))\n") == []


def test_every_migration_only_expands_unless_it_names_its_contract():
    assert VERSIONS, "no migrations found"
    offenders = {}
    for path in VERSIONS:
        source = path.read_text()
        steps = contract_steps(source)
        if steps and "# contract:" not in source:
            offenders[str(path.relative_to(VERSIONS[0].parents[4]))] = steps
    hint = "add '# contract: <release>' only when safe"
    assert not offenders, f"these migrations break the previous release ({hint}): {offenders}"
