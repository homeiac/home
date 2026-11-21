"""Export benchmark runs, selected slots and available diagnostics to a standalone DuckDB."""

import argparse
import re
import os
from pathlib import Path
import sqlite3

import duckdb

SCHEMAS = {
    "mac_factorial_runs": """block INTEGER, slots INTEGER, offered INTEGER, valid INTEGER, seconds DOUBLE,
        per_minute DOUBLE, p95_seconds DOUBLE, mean_gpu_percent DOUBLE, peak_rss_mib DOUBLE,
        starting_pressure INTEGER, peak_pressure INTEGER, error VARCHAR, PRIMARY KEY(block,slots,offered)""",
    "mac_factorial_items": """block INTEGER, slots INTEGER, offered INTEGER, item VARCHAR, kind VARCHAR,
        seconds DOUBLE, input_tokens INTEGER, output_tokens INTEGER, PRIMARY KEY(block,slots,offered,item)""",
}


def diagnostics(target, folder):
    for filename, table in (
        ("network.json", "mac_pilot_network"),
        ("network-replay.json", "mac_replay_network"),
        ("rtx-phases.json", "rtx_matched_phases"),
        ("cache-replay.json", "mac_cache_replay"),
        ("production-window.json", "production_throughput"),
    ):
        path = folder / filename
        if path.exists():
            target.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_json_auto(?)", [str(path)])
    for filename, table in (
        ("mac-counters.jsonl", "mac_hardware_samples"),
        ("mac-after-wake.jsonl", "mac_hardware_samples_after_wake"),
    ):
        counter_path = folder / filename
        if not counter_path.exists():
            continue
        target.execute(
            f"""CREATE OR REPLACE TABLE {table} AS
            SELECT timestamp, gpu_freq_mhz, gpu_power, gpu_active_ratio, temp.gpu_temp_avg AS gpu_celsius
            FROM read_json_auto(?)""",
            [str(counter_path)],
        )
    target.execute("""CREATE OR REPLACE TABLE mac_model_phases(
        block INTEGER, slots INTEGER, offered INTEGER, task INTEGER, phase VARCHAR, seconds DOUBLE, tokens INTEGER)""")
    pattern = re.compile(r"task (\d+) \|\s*(prompt eval time|eval time) =\s*([\d.]+) ms /\s*(\d+) tokens")
    records = []
    for path in folder.glob("block-*-*-*.log"):
        block, slots, offered = map(int, path.stem.split("-")[1:])
        for match in pattern.finditer(path.read_text()):
            if int(match[1]) != 0:  # Exclude the untimed warmup.
                records.append(
                    (
                        block,
                        slots,
                        offered,
                        int(match[1]),
                        "prompt" if match[2].startswith("prompt") else "generation",
                        float(match[3]) / 1000,
                        int(match[4]),
                    )
                )
    if records:
        target.executemany("INSERT INTO mac_model_phases VALUES (?,?,?,?,?,?,?)", records)
    decision = folder / "decision.json"
    if decision.exists():
        target.execute(
            """CREATE OR REPLACE TABLE mac_slot_decision AS
            SELECT selected.slots AS slots, selected.offered AS offered FROM read_json_auto(?)""",
            [str(decision)],
        )


def export(source, output):
    os.umask(0o077)
    temporary = output.with_name(output.name + ".new")
    with (
        sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as data,
        duckdb.connect(str(temporary)) as target,
    ):
        for name, schema in SCHEMAS.items():
            rows = data.execute(f"SELECT * FROM {name}").fetchall()
            if not rows:
                raise ValueError(f"Missing evaluation data in {name}")
            target.execute(f"CREATE OR REPLACE TABLE {name} ({schema})")
            placeholders = ", ".join("?" for _ in rows[0])
            target.executemany(f"INSERT INTO {name} VALUES ({placeholders})", rows)
        for name in SCHEMAS:
            archived = name + "_excluded"
            if data.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [archived]
            ).fetchone():
                rows = data.execute(f"SELECT * FROM {archived}").fetchall()
                target.execute(
                    f"CREATE OR REPLACE TABLE {archived} AS SELECT *, NULL::VARCHAR AS reason FROM {name} WHERE false"
                )
                if rows:
                    target.executemany(
                        f"INSERT INTO {archived} VALUES ({','.join('?' for _ in rows[0])})", rows
                    )
        diagnostics(target, source.parent)
    temporary.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.source, args.output)
