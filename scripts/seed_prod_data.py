"""
Seed PRD_SNOWHEALTH_ML_DB.SNOWHEALTH_RAW.SNOWHEALTH_DEMAND_TRANSACTIONS.

Stand-in for a production ingestion pipeline: generates an independent synthetic
sample (different seed from DEV's notebook 01) so PROD trains on its own data.
Run once by an admin — CI never writes raw data.

    python scripts/seed_prod_data.py --connection <admin_connection>
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "source"))

from snowflake.snowpark import Session  # noqa: E402
from synthetic_data import generate_transactions  # noqa: E402

TABLE = "PRD_SNOWHEALTH_ML_DB.SNOWHEALTH_RAW.SNOWHEALTH_DEMAND_TRANSACTIONS"

parser = argparse.ArgumentParser()
parser.add_argument("--connection", required=True)
parser.add_argument("--rows", type=int, default=10000)
parser.add_argument("--seed", type=int, default=2026)
args = parser.parse_args()

session = Session.builder.config("connection_name", args.connection).create()
session.use_role("SNOWHEALTH_PROD_DEPLOYER")
session.use_warehouse("COMPUTE_WH")

df = generate_transactions(n_rows=args.rows, seed=args.seed)
for c in ("PROMOTION_FLAG", "IS_WEEKEND", "IS_HOLIDAY"):
    df[c] = df[c].astype(bool)

session.create_dataframe(df).write.mode("overwrite").save_as_table(TABLE)
print(f"Loaded {session.table(TABLE).count():,} rows into {TABLE} (seed={args.seed})")
