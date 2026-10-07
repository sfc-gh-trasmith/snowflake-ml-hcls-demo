"""
SNOWHEALTH Pipeline - Step 3: Model Evaluation
Runs batch inference, evaluates model quality, enforces quality gate.
"""
from snowflake.snowpark.context import get_active_session
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from snowflake.ml.registry import Registry
import pandas as pd
import numpy as np

session = get_active_session()
print('Step 3: Model Evaluation - Started')

# Load model from registry
registry = Registry(session=session, database_name='SNOWHEALTH_ML_DB', schema_name='SNOWHEALTH_MODELS')
mv = registry.get_model('SNOWHEALTH_PIPELINE_MODEL').version('v1')
print('Model loaded: SNOWHEALTH_PIPELINE_MODEL v1')

# Load test data
df = session.table('SNOWHEALTH_ML_DB.SNOWHEALTH_FEATURES.SNOWHEALTH_PIPELINE_FEATURES').to_pandas()
exclude = ['TRANSACTION_ID','TRANSACTION_DATE','STORE_ID','SKU_ID','PRODUCT_NAME',
           'REGION','PRODUCT_CATEGORY','FULFILLMENT_CHANNEL','EVENT_TIMESTAMP','UNITS_SOLD']
feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype in ['int64','float64']]

X = df[feature_cols].astype(float)
y = df['UNITS_SOLD'].astype(float)
_, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
_, df_meta, _, _ = train_test_split(df, y, test_size=0.2, random_state=42)

# Run batch inference
predictions = mv.run(X_test)
pred_vals = predictions.iloc[:, 0].values

# Compute metrics
mae = mean_absolute_error(y_test, pred_vals)
rmse = np.sqrt(mean_squared_error(y_test, pred_vals))
r2 = r2_score(y_test, pred_vals)
print(f'Evaluation: MAE={mae:.4f}, RMSE={rmse:.4f}, R2={r2:.4f}')

# Quality gate
RMSE_THRESHOLD = 10.0
if rmse > RMSE_THRESHOLD:
    raise ValueError(f'Model quality gate FAILED: RMSE {rmse:.4f} > threshold {RMSE_THRESHOLD}')
print(f'Quality gate PASSED: RMSE {rmse:.4f} < {RMSE_THRESHOLD}')

# Save evaluation results
eval_df = df_meta[['STORE_ID','SKU_ID','REGION','PRODUCT_CATEGORY']].copy().reset_index(drop=True)
eval_df['ACTUAL'] = y_test.values
eval_df['PREDICTION'] = pred_vals
eval_df['RESIDUAL'] = eval_df['ACTUAL'] - eval_df['PREDICTION']
eval_df['PREDICTION_TIMESTAMP'] = pd.Timestamp.now()
for c in eval_df.select_dtypes(include=['int8','int16','int32']).columns:
    eval_df[c] = eval_df[c].astype('int64')

session.create_dataframe(eval_df).write.mode('overwrite').save_as_table(
    'SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_EVAL_RESULTS'
)
print(f'Step 3 COMPLETE: Saved {len(eval_df)} evaluation results')
