"""
SnowHealth Pipeline — Step 1: Feature Engineering
Loads raw transactions, engineers features, saves to pipeline feature table.

Environment variables (set by DCM templating via env_vars):
  - DCM_DATABASE: target database (e.g. DEV_SNOWHEALTH_ML_DB, PRD_SNOWHEALTH_ML_DB)
  - DCM_SCHEMA: target schema (e.g. SNOWHEALTH_MODELS)
"""

import os

import numpy as np
import pandas as pd
from snowflake.snowpark.context import get_active_session

session = get_active_session()
print("Step 1: Feature Engineering — Started")

DB = os.environ.get("DCM_DATABASE", "DEV_SNOWHEALTH_ML_DB")
SCHEMA = os.environ.get("DCM_SCHEMA", "SNOWHEALTH_MODELS")
print(f"Target: {DB}.{SCHEMA}")

# Load raw transactions
df = session.table(f"{DB}.SNOWHEALTH_RAW.SNOWHEALTH_DEMAND_TRANSACTIONS").to_pandas()
print(f"Loaded {len(df):,} raw transactions")

# Calendar features
df["TRANSACTION_DATE"] = pd.to_datetime(df["TRANSACTION_DATE"])
df["MONTH"] = df["TRANSACTION_DATE"].dt.month
df["QUARTER"] = df["TRANSACTION_DATE"].dt.quarter
df["WEEK_OF_YEAR"] = df["TRANSACTION_DATE"].dt.isocalendar().week.astype(int)
df["IS_WEEKEND_INT"] = df["IS_WEEKEND"].astype(int)
df["IS_HOLIDAY_INT"] = df["IS_HOLIDAY"].astype(int)
df["IS_PROMOTION_INT"] = df["PROMOTION_FLAG"].astype(int)

# Cyclical encoding
df["MONTH_SIN"] = np.sin(2 * np.pi * df["MONTH"] / 12)
df["MONTH_COS"] = np.cos(2 * np.pi * df["MONTH"] / 12)
df["DOW_SIN"] = np.sin(2 * np.pi * df["DAY_OF_WEEK"] / 7)
df["DOW_COS"] = np.cos(2 * np.pi * df["DAY_OF_WEEK"] / 7)

# Lag + rolling features
df = df.sort_values(["SKU_ID", "STORE_ID", "TRANSACTION_DATE"])
grp = ["SKU_ID", "STORE_ID"]
df["ROLLING_7D_AVG"] = df.groupby(grp)["UNITS_SOLD"].transform(
    lambda x: x.rolling(7, min_periods=1).mean()
)
df["ROLLING_30D_AVG"] = df.groupby(grp)["UNITS_SOLD"].transform(
    lambda x: x.rolling(30, min_periods=1).mean()
)
df["LAG_7D"] = df.groupby(grp)["UNITS_SOLD"].shift(7).fillna(df["UNITS_SOLD"].median())
df["LAG_14D"] = (
    df.groupby(grp)["UNITS_SOLD"].shift(14).fillna(df["UNITS_SOLD"].median())
)

# Interaction features
df["PRICE_X_PROMO"] = df["UNIT_PRICE"] * df["PROMOTION_DISCOUNT_PCT"]
df["INVENTORY_TURNOVER"] = np.where(
    df["INVENTORY_ON_HAND"] > 0, df["UNITS_SOLD"] / df["INVENTORY_ON_HAND"], 0
)
seasonal_map = {
    1: 0.8,
    2: 0.9,
    3: 1.0,
    4: 1.1,
    5: 1.2,
    6: 1.1,
    7: 1.0,
    8: 0.9,
    9: 1.1,
    10: 1.2,
    11: 1.3,
    12: 1.1,
}
df["SEASONAL_INDEX"] = df["MONTH"].map(seasonal_map)

# Select columns and save
keep = [
    "TRANSACTION_ID",
    "TRANSACTION_DATE",
    "STORE_ID",
    "SKU_ID",
    "PRODUCT_NAME",
    "REGION",
    "PRODUCT_CATEGORY",
    "FULFILLMENT_CHANNEL",
    "UNITS_SOLD",
    "UNIT_PRICE",
    "PROMOTION_DISCOUNT_PCT",
    "DAY_OF_WEEK",
    "IS_WEEKEND_INT",
    "IS_HOLIDAY_INT",
    "IS_PROMOTION_INT",
    "TEMPERATURE_F",
    "FLU_INDEX",
    "STORE_SIZE_SQFT",
    "STAFF_COUNT",
    "COMPETITOR_PROXIMITY_MILES",
    "INVENTORY_ON_HAND",
    "DAYS_SUPPLY_ON_HAND",
    "LEAD_TIME_DAYS",
    "MONTH",
    "QUARTER",
    "WEEK_OF_YEAR",
    "MONTH_SIN",
    "MONTH_COS",
    "DOW_SIN",
    "DOW_COS",
    "ROLLING_7D_AVG",
    "ROLLING_30D_AVG",
    "LAG_7D",
    "LAG_14D",
    "PRICE_X_PROMO",
    "INVENTORY_TURNOVER",
    "SEASONAL_INDEX",
]
df_save = df[keep].copy()
for c in df_save.select_dtypes(include=["int8", "int16", "int32"]).columns:
    df_save[c] = df_save[c].astype("int64")

session.create_dataframe(df_save.reset_index(drop=True)).write.mode(
    "overwrite"
).save_as_table(f"{DB}.{SCHEMA}.SNOWHEALTH_PIPELINE_FEATURES")
print(f"Step 1 COMPLETE: Saved {len(df_save):,} rows with {len(keep)} features")
