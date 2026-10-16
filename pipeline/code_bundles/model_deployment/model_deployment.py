"""
SnowHealth Pipeline — Step 3: Model Deployment
Evaluates a model version, enforces quality gate, promotes to default.

Environment variables (set by DCM templating via env_vars):
  - DCM_DATABASE: target database
  - DCM_SCHEMA: target schema
  - MODEL_VERSION: "latest" (auto) or specific version name (pinned)

Usage:
  DEV (auto):  snow dcm deploy --from pipeline --target DEV
  PROD (pin):  snow dcm deploy --from pipeline --target PROD --variable model_version=PIPELINE_20261012_v3
"""

import os

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from snowflake.ml.registry import Registry
from snowflake.snowpark.context import get_active_session

session = get_active_session()
print("Step 3: Model Deployment — Started")

DB = os.environ.get("DCM_DATABASE", "DEV_SNOWHEALTH_ML_DB")
SCHEMA = os.environ.get("DCM_SCHEMA", "SNOWHEALTH_MODELS")
model_version = os.environ.get("MODEL_VERSION", "latest")
print(f"Target: {DB}.{SCHEMA} | MODEL_VERSION={model_version}")

# Load model registry
registry = Registry(session=session, database_name=DB, schema_name=SCHEMA)
model_ref = registry.get_model("SNOWHEALTH_PIPELINE_MODEL")

if model_version == "latest":
    versions = model_ref.versions()
    target = versions[-1]
    print(f"Auto-selected latest version: {target.version_name}")
else:
    target = model_ref.version(model_version)
    print(f"Using pinned version: {target.version_name}")

# Load test data for evaluation
df = session.table(f"{DB}.{SCHEMA}.SNOWHEALTH_PIPELINE_FEATURES").to_pandas()
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

X = df[feature_cols].astype(float)
y = df["UNITS_SOLD"].astype(float)
_, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Batch inference on holdout set
predictions = target.run(X_test, function_name="predict")
pred_vals = predictions.iloc[:, 0].values

# Compute metrics
mae = mean_absolute_error(y_test, pred_vals)
rmse = float(np.sqrt(mean_squared_error(y_test, pred_vals)))
r2 = r2_score(y_test, pred_vals)
print(f"Evaluation: MAE={mae:.3f}, RMSE={rmse:.3f}, R2={r2:.3f}")

# Quality gate
RMSE_THRESHOLD = 15.0
if rmse > RMSE_THRESHOLD:
    raise ValueError(
        f"QUALITY GATE FAILED: RMSE {rmse:.3f} exceeds threshold {RMSE_THRESHOLD}"
    )
print(f"Quality gate PASSED: RMSE {rmse:.3f} < {RMSE_THRESHOLD}")

# Promote to default version
model_ref.default = target.version_name
print(f"Default version set to: {target.version_name}")

# Smoke test (5 predictions)
smoke = target.run(X_test.head(5), function_name="predict")
print(f"Smoke test: {len(smoke)} predictions returned")

# Log deployment result
deploy_log = pd.DataFrame(
    [
        {
            "MODEL_NAME": "SNOWHEALTH_PIPELINE_MODEL",
            "VERSION": target.version_name,
            "DEPLOYED_AT": pd.Timestamp.now(),
            "RMSE": rmse,
            "STATUS": "DEPLOYED",
        }
    ]
)
session.create_dataframe(deploy_log).write.mode("append").save_as_table(
    f"{DB}.{SCHEMA}.SNOWHEALTH_PIPELINE_DEPLOY_LOG"
)
print(f"Step 3 COMPLETE: {target.version_name} deployed as default")
