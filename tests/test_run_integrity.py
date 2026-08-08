from jitendex_ru.db import connect, initialize
from jitendex_ru.run_integrity import run_history_fingerprint, source_identity_report


def _seed(connection):
    connection.execute(
        "INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) "
        "VALUES ('jitendex','v','u','j','j','e'),('kaishi','v','u','k','k','e')"
    )
    for run_id in (2, 3):
        connection.execute(
            """INSERT INTO run(id,jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,
            extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (run_id, 1, 2, f"s-{run_id}", "e", f"p-{run_id}", "r", "t", "{}"),
        )
        connection.execute(
            """INSERT INTO article(id,snapshot_id,bank_number,entry_ordinal,expression,reading,
            sequence,raw_json,source_sha256,selected) VALUES (?,?,?,?,?,?,?,?,?,1)""",
            (run_id, 1, run_id, 0, "月", "つき", run_id, "[]", f"a-{run_id}"),
        )
        connection.execute(
            """INSERT INTO translation_unit(id,run_id,article_id,json_pointer,role,source_text,
            source_sha256,byte_count) VALUES (?,?,?,?,?,?,?,?)""",
            (f"u-{run_id}", run_id, run_id, "/x", "tooltip", "moon", "same-source", 4),
        )


def test_source_identity_reports_exact_multiset_differences(tmp_path):
    path = tmp_path / "db.sqlite3"
    initialize(path)
    with connect(path) as connection:
        _seed(connection)
        report = source_identity_report(connection, 3, 2)
        assert report["missing_from_candidate"] == 1
        assert report["extra_in_candidate"] == 1
        assert report["passed"] is False


def test_history_fingerprint_is_run_scoped(tmp_path):
    path = tmp_path / "db.sqlite3"
    initialize(path)
    with connect(path) as connection:
        _seed(connection)
        before = run_history_fingerprint(connection, 2)
        connection.execute("UPDATE run SET state='complete' WHERE id=3")
        assert run_history_fingerprint(connection, 2) == before
        connection.execute("UPDATE run SET state='complete' WHERE id=2")
        assert run_history_fingerprint(connection, 2)["sha256"] != before["sha256"]
