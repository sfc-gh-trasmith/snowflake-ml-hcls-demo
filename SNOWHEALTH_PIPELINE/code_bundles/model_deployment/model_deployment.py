"""
SNOWHEALTH Pipeline - Step 4: Model Deployment
Sets trained model as default and updates monitoring source table.
"""
from snowflake.snowpark.context import get_active_session
from snowflake.ml.registry import Registry
import pandas as pd

session = get_active_session()
print('Step 4: Model Deployment - Started')

# Set model as default version
registry = Registry(session=session, database_name='SNOWHEALTH_ML_DB', schema_name='SNOWHEALTH_MODELS')
model_ref = registry.get_model('SNOWHEALTH_PIPELINE_MODEL')
model_ref.default = 'v1'
print('Default version set to v1')

# Verify deployment
mv = model_ref.version('v1')
funcs = [f['name'] for f in mv.show_functions()]
print(f'Model functions: {funcs}')

# Run a smoke test (5 rows)
df = session.table('SNOWHEALTH_ML_DB.SNOWHEALTH_FEATURES.SNOWHEALTH_PIPELINE_FEATURES').to_pandas()
exclude = ['TRANSACTION_ID','TRANSACTION_DATE','STORE_ID','SKU_ID','PRODUCT_NAME',
           'REGION','PRODUCT_CATEGORY','FULFILLMENT_CHANNEL','EVENT_TIMESTAMP','UNITS_SOLD']
feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype in ['int64','float64']]
test_input = df[feature_cols].head(5).astype(float)

smoke_test = mv.run(test_input)
print(f'Smoke test passed: {len(smoke_test)} predictions')
print(smoke_test)

# Update deployment log
deploy_log = pd.DataFrame([{
    'MODEL_NAME': 'SNOWHEALTH_PIPELINE_MODEL',
    'VERSION': 'v1',
    'DEPLOYED_AT': pd.Timestamp.now(),
    'STATUS': 'DEPLOYED',
    'SMOKE_TEST': 'PASSED'
}])
session.create_dataframe(deploy_log).write.mode('append').save_as_table(
    'SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_DEPLOY_LOG'
)
print('Step 4 COMPLETE: Model deployed and verified')
