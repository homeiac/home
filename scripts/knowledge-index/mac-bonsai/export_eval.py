"""Copy the two numeric evaluation tables into a standalone DuckDB for comparison."""

import argparse
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
    temporary.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.source, args.output)
