"""db/schema.sql and backend/app/db.py must describe the same tables."""

import re
from pathlib import Path

from app.db import metadata

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def columns_in_schema_sql() -> dict[str, set[str]]:
    sql = re.sub(r"--[^\n]*", "", SCHEMA.read_text())  # drop comments
    tables = {}
    for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", sql, re.S):
        tables[name] = {line.split()[0] for line in body.splitlines() if line.strip()}
    return tables


def test_schema_sql_matches_sqlalchemy_tables():
    sql_tables = columns_in_schema_sql()
    assert set(sql_tables) == set(metadata.tables)
    for name, table in metadata.tables.items():
        assert sql_tables[name] == {c.name for c in table.columns}, name
