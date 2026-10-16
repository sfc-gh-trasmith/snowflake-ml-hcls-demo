"""
SnowHealth Pipeline — Step 2: Model Training
Trains XGBoost on pipeline features, registers to Snowflake Model Registry.

Environment variables (set by DCM templating via env_vars):
  - DCM_DATABASE: target database
  - DCM_SCHEMA: target schema
"""

import os
import time

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from snowflake.ml.registry import Registry
from snowflake.snowpark.context import get_active_session
from xgboost import XGBRegressor

session = get_active_session()
print("Step 2: Model Training — Started")

DB = os.environ.get("DCM_DATABASE", "DEV_SNOWHEALTH_ML_DB")
SCHEMA = os.environ.get("DCM_SCHEMA", "SNOWHEALTH_MODELS")
print(f"Target: {DB}.{SCHEMA}")

# Load pipeline features
df = session.table(f"{DB}.{SCHEMA}.SNOWHEALTH_PIPELINE_FEATURES").to_pandas()
print(f"Loaded {len(df):,} feature rows")

# Identify numeric feature columns (exclude metadata and target)
exclude = {
    "TRANSACTION_ID",
    "TRANSACTION_DATE",
    "STORE_ID",
    "SKU_ID",
    "PRODUCT_NAME",
    "REGION",
    "PRODUCT_CATEGORY",
    "FULFILLMENT_CHANNEL",
    "UNITS_SOLD",
}
feature_cols = [
    c for c in df.columns if c not in exclude and df[c].dtype in ("int64", "float64")
]
print(f"Features: {len(feature_cols)}")

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
    comment=f"Pipeline XGBoost (RMSE={rmse:.3f})",
)
print(f"Step 2 COMPLETE: Registered SNOWHEALTH_PIPELINE_MODEL version {version_name}")
