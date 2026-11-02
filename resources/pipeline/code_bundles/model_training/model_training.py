"""
SnowHealth Pipeline — Step 2: Model Training
Builds a point-in-time training set from the declarative Feature Store
(SNOWHEALTH_PIPELINE_FV/V1), trains XGBoost, registers to Model Registry.

Environment variables (set by DCM templating via env_vars):
  - DCM_DATABASE: target database
  - DCM_SCHEMA: target schema
  - FS_SCHEMA: feature store schema (managed by `snow feature apply`)
  - FV_NAME / FV_VERSION: feature view to train from
"""

import os
import time

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from snowflake.ml.feature_store import CreationMode, FeatureStore
from snowflake.ml.registry import Registry
from snowflake.snowpark import functions as F
from snowflake.snowpark.context import get_active_session
from xgboost import XGBRegressor

session = get_active_session()
print("Step 2: Model Training — Started")

DB = os.environ.get("DCM_DATABASE", "DEV_SNOWHEALTH_ML_DB")
SCHEMA = os.environ.get("DCM_SCHEMA", "SNOWHEALTH_MODELS")
FS_SCHEMA = os.environ.get("FS_SCHEMA", "SNOWHEALTH_PIPELINE_FS")
FV_NAME = os.environ.get("FV_NAME", "SNOWHEALTH_PIPELINE_FV")
FV_VERSION = os.environ.get("FV_VERSION", "V1")
print(f"Target: {DB}.{SCHEMA} | Feature view: {DB}.{FS_SCHEMA}.{FV_NAME}/{FV_VERSION}")

# Feature view is declared in feature_store/ and deployed by `snow feature apply`
fs = FeatureStore(
    session=session,
    database=DB,
    name=FS_SCHEMA,
    default_warehouse=session.get_current_warehouse(),
    creation_mode=CreationMode.FAIL_IF_NOT_EXIST,
)
fv = fs.get_feature_view(FV_NAME, FV_VERSION)
feature_cols = [c.strip('"') for c in fv.feature_names]

# Spine: entity key + event timestamp + label from raw transactions
spine = session.table(f"{DB}.SNOWHEALTH_RAW.SNOWHEALTH_DEMAND_TRANSACTIONS").select(
    "TRANSACTION_ID",
    F.to_timestamp_ntz("TRANSACTION_DATE").alias("TRANSACTION_DATE"),
    "UNITS_SOLD",
)

# Point-in-time (ASOF) join of features onto the spine
df = (
    fs.generate_training_set(
        spine_df=spine,
        features=[fv],
        spine_timestamp_col="TRANSACTION_DATE",
        spine_label_cols=["UNITS_SOLD"],
    )
    .sort("TRANSACTION_ID")
    .to_pandas()
)
print(f"Training set: {len(df):,} rows, {len(feature_cols)} features")
if df[feature_cols].isna().all(axis=1).any():
    raise ValueError("Spine rows with no matching features — feature view is stale")

X = df[feature_cols].astype(float)
y = df["UNITS_SOLD"].astype(float)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Train XGBoost
model = XGBRegressor(
    n_estimators=300,
    max_depth=8,
    learning_rate=0.05,
    subsample=0.9,
    colsample_bytree=1.0,
    min_child_weight=5,
    reg_alpha=0.1,
    reg_lambda=1.0,
    objective="reg:squarederror",
    tree_method="hist",
    random_state=42,
)
model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

# Evaluate on holdout
preds = model.predict(X_test)
mae = mean_absolute_error(y_test, preds)
rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
r2 = r2_score(y_test, preds)
print(f"Holdout metrics: MAE={mae:.3f}, RMSE={rmse:.3f}, R2={r2:.3f}")

# Register to Model Registry
registry = Registry(session=session, database_name=DB, schema_name=SCHEMA)

# Generate a version name based on timestamp
version_name = f"PIPELINE_{time.strftime('%Y%m%d_%H%M')}"

try:
    existing = registry.get_model("SNOWHEALTH_PIPELINE_MODEL")
    print(f"Model exists — adding version {version_name}")
except Exception:  # noqa: BLE001 — model may not exist yet
    print("Creating new model SNOWHEALTH_PIPELINE_MODEL")

mv = registry.log_model(
    model,
    model_name="SNOWHEALTH_PIPELINE_MODEL",
    version_name=version_name,
    sample_input_data=X_train.head(10),
    metrics={"mae": mae, "rmse": rmse, "r2": r2},
    target_platforms=["WAREHOUSE"],
    comment=f"Pipeline XGBoost (RMSE={rmse:.3f}) trained on {FS_SCHEMA}.{FV_NAME}/{FV_VERSION}",
)
print(f"Step 2 COMPLETE: Registered SNOWHEALTH_PIPELINE_MODEL version {version_name}")
