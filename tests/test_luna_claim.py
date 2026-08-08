from jitendex_ru.batch import claim
from jitendex_ru.db import connect, initialize


def _seed_runs_and_batches(connection, tmp_path):
    connection.execute(
        "INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) "
        "VALUES ('jitendex','v','u','j','j','e')"
    )
    connection.execute(
        "INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) "
        "VALUES ('kaishi','v','u','k','k','e')"
    )
    for run_id in (1, 2):
        connection.execute(
            """INSERT INTO run(id,jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,
            extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (run_id, 1, 2, f"selection-{run_id}", "e", f"p-{run_id}", f"rp-{run_id}", "t", "{}"),
        )
    for batch_id, run_id, kind in (
        ("b-run1", 1, "translation"),
        ("b-run2", 2, "translation"),
        ("rb-run2", 2, "review"),
    ):
        manifest = tmp_path / f"{batch_id}.json"
        manifest.write_text("{}", encoding="utf-8")
        connection.execute(
            """INSERT INTO batch(id,run_id,kind,manifest_sha256,serialized_bytes,
            article_count,unit_count,manifest_path) VALUES (?,?,?,?,?,?,?,?)""",
            (batch_id, run_id, kind, f"hash-{batch_id}", 2, 0, 0, str(manifest)),
        )
    connection.commit()


def test_claim_is_scoped_to_run_and_kind_and_records_luna(tmp_path):
    path = tmp_path / "progress.sqlite3"
    initialize(path)
    with connect(path) as connection:
        _seed_runs_and_batches(connection, tmp_path)

        assert claim(
            connection, "translator", tmp_path / "outbox", run_id=1, kind="review",
            batch_id="b-run1", model_id="gpt-5.6-terra", reasoning_effort="medium",
            transport="responses-sync",
        ) is None
        task = claim(
            connection, "translator", tmp_path / "outbox", run_id=2, kind="translation",
            model_id="gpt-5.6-luna", reasoning_effort="medium", transport="responses-sync",
        )

        assert task["batch_id"] == "b-run2"
        attempt = connection.execute("SELECT * FROM attempt WHERE id=?", (task["attempt_id"],)).fetchone()
        assert attempt["model"] == "gpt-5.6-luna"
        assert attempt["reasoning_effort"] == "medium"
        assert attempt["transport"] == "responses-sync"
        assert connection.execute("SELECT state FROM batch WHERE id='b-run1'").fetchone()[0] == "ready"
        assert connection.execute("SELECT state FROM batch WHERE id='rb-run2'").fetchone()[0] == "ready"


def test_batch_claim_uses_attempt_id_as_custom_id(tmp_path):
    path = tmp_path / "progress.sqlite3"
    initialize(path)
    with connect(path) as connection:
        _seed_runs_and_batches(connection, tmp_path)
        task = claim(
            connection, "translator", tmp_path / "outbox", run_id=1, kind="translation",
            model_id="gpt-5.6-luna", reasoning_effort="medium", transport="batch-api",
        )

        attempt = connection.execute("SELECT * FROM attempt WHERE id=?", (task["attempt_id"],)).fetchone()
        assert attempt["api_custom_id"] == task["attempt_id"]
