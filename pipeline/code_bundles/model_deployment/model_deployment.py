"""
SnowHealth Pipeline — Step 3: Model Deployment
Evaluates the latest model version, enforces quality gate, promotes to default.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from snowflake.ml.registry import Registry
from snowflake.snowpark.context import get_active_session

session = get_active_session()
print("Step 3: Model Deployment — Started")

# Load model registry and get the latest version
registry = Registry(
    session=session, database_name="SNOWHEALTH_ML_DB", schema_name="SNOWHEALTH_MODELS"
)
model_ref = registry.get_model("SNOWHEALTH_PIPELINE_MODEL")
versions = model_ref.versions()
latest = versions[-1]
print(f"Latest version: {latest.version_name}")

# Load test data for evaluation
df = session.table(
    "SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_FEATURES"
).to_pandas()
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
predictions = latest.run(X_test)
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
model_ref.default = latest.version_name
print(f"Default version set to: {latest.version_name}")

# Smoke test (5 predictions)
smoke = latest.run(X_test.head(5))
print(f"Smoke test: {len(smoke)} predictions returned")

# Log deployment result
deploy_log = pd.DataFrame(
    [
        {
            "MODEL_NAME": "SNOWHEALTH_PIPELINE_MODEL",
            "VERSION": latest.version_name,
            "DEPLOYED_AT": pd.Timestamp.now(),
            "RMSE": rmse,
            "STATUS": "DEPLOYED",
        }
    ]
)
session.create_dataframe(deploy_log).write.mode("append").save_as_table(
    "SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_DEPLOY_LOG"
)
print(f"Step 3 COMPLETE: {latest.version_name} deployed as default")
