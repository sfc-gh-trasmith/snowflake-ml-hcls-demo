"""
SNOWHEALTH Pipeline - Step 2: Model Training
Trains XGBoost on engineered features, registers model to Snowflake Model Registry.
"""
from snowflake.snowpark.context import get_active_session
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor
from snowflake.ml.registry import Registry
from snowflake.ml.model.model_signature import infer_signature
import pandas as pd
import numpy as np

session = get_active_session()
print('Step 2: Model Training - Started')

# Load features
df = session.table('SNOWHEALTH_ML_DB.SNOWHEALTH_FEATURES.SNOWHEALTH_PIPELINE_FEATURES').to_pandas()
print(f'Loaded {len(df)} feature rows')

# Identify numeric feature columns
exclude = ['TRANSACTION_ID','TRANSACTION_DATE','STORE_ID','SKU_ID','PRODUCT_NAME',
           'REGION','PRODUCT_CATEGORY','FULFILLMENT_CHANNEL','EVENT_TIMESTAMP','UNITS_SOLD']
feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype in ['int64','float64']]
print(f'Using {len(feature_cols)} features')

X = df[feature_cols].astype(float)
y = df['UNITS_SOLD'].astype(float)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train XGBoost
model = XGBRegressor(
    n_estimators=300, max_depth=8, learning_rate=0.05,
    subsample=0.9, colsample_bytree=1.0, min_child_weight=5,
    reg_alpha=0.1, reg_lambda=1.0,
    objective='reg:squarederror', tree_method='hist', random_state=42
)
model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

# Evaluate
preds = model.predict(X_test)
mae = mean_absolute_error(y_test, preds)
rmse = np.sqrt(mean_squared_error(y_test, preds))
r2 = r2_score(y_test, preds)
print(f'MAE={mae:.4f}, RMSE={rmse:.4f}, R2={r2:.4f}')

# Register to Model Registry
registry = Registry(session=session, database_name='SNOWHEALTH_ML_DB', schema_name='SNOWHEALTH_MODELS')
sig = infer_signature(X_train.head(10), y_train.head(10))

try:
    session.sql('DROP MODEL IF EXISTS SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_MODEL').collect()
except:
    pass

mv = registry.log_model(
    model, model_name='SNOWHEALTH_PIPELINE_MODEL', version_name='v1',
    signatures={'predict': sig},
    metrics={'mae': mae, 'rmse': float(rmse), 'r2': r2},
    sample_input_data=X_train.head(10),
    target_platforms=['WAREHOUSE'],
    comment=f'Pipeline-trained XGBoost (RMSE={rmse:.4f})'
)
print(f'Step 2 COMPLETE: Model registered as SNOWHEALTH_PIPELINE_MODEL v1')
