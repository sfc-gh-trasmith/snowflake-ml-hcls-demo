# SnowHealth ML Pipeline — Code Bundles & Pipeline Builder

## Overview

DCM-managed ML pipeline that automates weekly retraining and deployment of the SnowHealth demand forecasting model. Demonstrates the **Pipeline Builder** and **Code Bundles** features — infrastructure-as-code for ML workflows.

## DAG Structure

```
SNOWHEALTH_PIPELINE_ROOT (weekly Monday 6 AM ET)
  └─> SNOWHEALTH_TASK_FEATURE_ENGINEERING
        └─> SNOWHEALTH_TASK_MODEL_TRAINING
              └─> SNOWHEALTH_TASK_MODEL_DEPLOYMENT (quality gate → promote → smoke test)
```

## Project Structure

```
pipeline/
├── manifest.yml                              DCM project config (target, owner)
├── sources/definitions/
│   └── pipeline.yml                          3 code bundles + 4 tasks (DAG)
└── code_bundles/
    ├── feature_engineering/
    │   ├── code_bundle.yml                   custom + warehouse + python 3.12
    │   └── feature_engineering.py            30+ features from raw transactions
    ├── model_training/
    │   ├── code_bundle.yml
    │   └── model_training.py                 XGBoost → Model Registry
    └── model_deployment/
        ├── code_bundle.yml
        └── model_deployment.py               Evaluate → quality gate → promote default
```

## Pipeline Steps

| Step | Code Bundle | What It Does |
|------|------------|-------------|
| **1. Feature Engineering** | `feature_engineering.py` | Loads 10K raw transactions, engineers 30+ features (calendar, cyclical, lag, rolling, interaction), saves to `SNOWHEALTH_PIPELINE_FEATURES` |
| **2. Model Training** | `model_training.py` | Trains XGBoost regressor (300 trees, depth 8), registers timestamped version to Model Registry |
| **3. Model Deployment** | `model_deployment.py` | Batch evaluation on holdout, enforces RMSE < 15.0 quality gate, promotes to default version, runs smoke test |

## Deploy & Run

```bash
# Deploy to Snowflake
snow dcm deploy --from pipeline --target DEV
```

```sql
-- Resume the DAG
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_ROOT RESUME;

-- Trigger a manual run
EXECUTE TASK SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_ROOT;

-- Check run history
SELECT NAME, STATE, SCHEDULED_TIME, COMPLETED_TIME, ERROR_MESSAGE
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
))
WHERE NAME LIKE 'SNOWHEALTH_%'
ORDER BY SCHEDULED_TIME DESC;
```

## Teardown

```bash
snow dcm teardown --from pipeline --target DEV
```
