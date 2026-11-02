"""
Seed <ENV>_MLOPS_DB.RAW.MLOPS_DEMAND_TRANSACTIONS with synthetic source data.

Stand-in for a real ingestion pipeline (Snowpipe, Openflow, dbt, ...): each
environment gets an independent sample (different seed) so DEV and PROD train
on their own data. Run once by an admin — CI never writes source data.

    python scripts/seed_data.py --env DEV  --connection <admin_connection>
    python scripts/seed_data.py --env PROD --connection <admin_connection>
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "source"))

from snowflake.snowpark import Session  # noqa: E402
from synthetic_data import generate_transactions  # noqa: E402

ENVS = {
    "DEV": ("DEV_MLOPS_DB", "MLOPS_DEV_DEPLOYER", 42),
    "PROD": ("PRD_MLOPS_DB", "MLOPS_PROD_DEPLOYER", 2026),
}

parser = argparse.ArgumentParser()
parser.add_argument("--env", required=True, choices=ENVS)
parser.add_argument("--connection", required=True)
parser.add_argument("--rows", type=int, default=10000)
args = parser.parse_args()

database, role, seed = ENVS[args.env]
table = f"{database}.RAW.MLOPS_DEMAND_TRANSACTIONS"

session = Session.builder.config("connection_name", args.connection).create()
session.use_role(role)
session.use_warehouse("COMPUTE_WH")

df = generate_transactions(n_rows=args.rows, seed=seed)
for c in ("PROMOTION_FLAG", "IS_WEEKEND", "IS_HOLIDAY"):
    df[c] = df[c].astype(bool)

session.create_dataframe(df).write.mode("overwrite").save_as_table(table)
print(f"Loaded {session.table(table).count():,} rows into {table} (seed={seed})")
