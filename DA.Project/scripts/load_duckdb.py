"""
Phase 1 loader — load the generated parquet files into a DuckDB database.

Creates data/claims.duckdb with 7 tables read directly from parquet.
Idempotent: drops & recreates each table on every run.

Run:  python scripts/load_duckdb.py
"""
import os
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA_DIR = os.path.join(ROOT, "data")
PARQUET_DIR = os.path.join(DATA_DIR, "parquet")
DB_PATH = os.path.join(DATA_DIR, "claims.duckdb")

TABLES = [
    "raw_patients", "raw_encounters", "raw_claims", "raw_denials",
    "dim_carc_codes", "dim_providers", "dim_payers",
]


def main():
    con = duckdb.connect(DB_PATH)
    con.execute("CREATE SCHEMA IF NOT EXISTS main;")
    for t in TABLES:
        pq = os.path.join(PARQUET_DIR, f"{t}.parquet").replace("'", "''")
        con.execute(f"DROP TABLE IF EXISTS {t};")
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet('{pq}');")
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  loaded {t:16s} rows={n:6d}")

    # basic referential sanity
    orphan = con.execute("""
        SELECT count(*) FROM raw_claims c
        LEFT JOIN raw_encounters e USING (encounter_id)
        WHERE e.encounter_id IS NULL
    """).fetchone()[0]
    print(f"\nOrphan claims (no encounter): {orphan}")

    print(f"\nDuckDB ready at: {DB_PATH}")
    con.close()


if __name__ == "__main__":
    main()
