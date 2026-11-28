"""Exercise the Cricket publisher and shared-workload checker against disposable PostgreSQL."""
import copy
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from uuid import UUID

import pytest

from check_media_observations import check
from cricket.openlabel import publish, scene
from cricket.test_openlabel import inputs, schema, shared  # noqa: F401 -- shared pytest fixtures


@pytest.fixture
def local_pg():
    if os.getenv("CRICKET_TEST_LOCAL_POSTGRES") != "1":
        pytest.skip("Set CRICKET_TEST_LOCAL_POSTGRES=1 to start disposable PostgreSQL")
    import psycopg

    with TemporaryDirectory(prefix="cricket-pg-") as folder:
        data = str(Path(folder) / "data")
        subprocess.run(["initdb", "-D", data, "-U", "cricket_test", "-A", "trust", "--no-locale",
                        "--encoding=UTF8"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["pg_ctl", "-D", data, "-l", str(Path(folder) / "log"), "-o",
                        f"-c listen_addresses='' -c unix_socket_directories='{folder}'", "-w", "start"],
                       check=True, stdout=subprocess.DEVNULL)
        try:
            with psycopg.connect(host=folder, user="cricket_test", dbname="postgres", autocommit=True) as conn:
                yield conn
        finally:
            subprocess.run(["pg_ctl", "-D", data, "-m", "fast", "-w", "stop"], check=True,
                           stdout=subprocess.DEVNULL)


def test_publish_correct_retry_and_verify(local_pg, shared, schema, inputs):
    asset, registry, events = inputs
    album = str(UUID(int=1))
    asset_id = asset["id"]
    original = scene(shared, asset, registry, events)
    publish(local_pg, shared, album, {asset_id: original}, schema)
    events[0]["revision"] += 1
    events[0]["data"]["outcome"] = "four"
    corrected = scene(shared, asset, registry, events)
    for _ in range(2):
        publish(local_pg, shared, album, {asset_id: corrected}, schema)
    rows = [dict(album=album, asset=asset_id, revision=rev, digest=digest, scene=doc)
            for rev, digest, doc in local_pg.execute(
                "SELECT revision,digest,scene FROM openlabel_album_scene WHERE album=%s AND asset=%s ORDER BY revision",
                (album, asset_id))]
    assert [row["revision"] for row in rows] == [1, 2]
    assert [row["scene"] for row in rows] == [original, corrected]
    uid, = original["openlabel"]["actions"]
    refs = [dict(contract_version=1, workload="cricket-indexer", run_id="synthetic-readback",
                 album=album, asset=asset_id, revision=row["revision"], digest=row["digest"],
                 vocabulary_release="cricket-1", collection="actions", uid=uid, evidence_ref="fixture/review")
            for row in rows]
    assert check(refs, rows, json.loads(schema.read_text()))["distinct_scene_revisions_referenced"] == 2

    other_album = str(UUID(int=2))
    other = copy.deepcopy(original)
    other["openlabel"]["metadata"]["producer"] = "other-publisher"
    shared.persist(local_pg, other_album, {asset_id: other})
    with pytest.raises(ValueError, match="another producer"):
        publish(local_pg, shared, other_album, {asset_id: corrected}, schema)
    assert local_pg.execute("SELECT revision,scene FROM openlabel_album_scene WHERE album=%s",
                            (other_album,)).fetchall() == [(1, other)]
