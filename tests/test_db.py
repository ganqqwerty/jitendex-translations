from jitendex_ru.db import connect, initialize


def test_database_initializes_with_integrity(tmp_path):
    path = tmp_path / "progress.sqlite3"
    initialize(path)
    with connect(path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"source_snapshot", "article", "translation_unit", "batch", "attempt", "review", "export"} <= tables
