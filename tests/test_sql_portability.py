from pathlib import Path


FORBIDDEN = (
    "INSERT OR IGNORE", "INSERT OR REPLACE", "SELECT changes()",
    "lastrowid", "BEGIN IMMEDIATE", "PRAGMA ", ".executescript(",
)


def test_sqlite_only_sql_stays_in_backend_modules():
    root = Path(__file__).resolve().parents[1]
    allowed = {
        root / "src/jitendex_ru/db.py",
        root / "src/jitendex_ru/database.py",
        root / "src/jitendex_ru/database_tools.py",
    }
    violations = []
    for directory in (root / "src", root / "scripts"):
        for path in directory.rglob("*.py"):
            if path in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN:
                if token in text:
                    violations.append(f"{path.relative_to(root)}: {token}")
    assert not violations, "SQLite-only SQL outside backend modules:\n" + "\n".join(violations)


def test_distinct_ordering_selects_the_postgresql_order_key():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/jitendex_ru/batch.py").read_text(encoding="utf-8")
    assert "SELECT DISTINCT kn.id,kn.word" in source
    assert "ORDER BY kn.id" in source
