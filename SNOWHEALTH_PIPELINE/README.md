# SnowHealth ML Demand Forecast Pipeline

## Overview

DCM-managed ML pipeline that automates weekly retraining, evaluation, and deployment of the SNOWHEALTH demand forecasting model. The pipeline runs as a Snowflake Task DAG with code bundles executing on compute pools.

## DAG Structure

```
SNOWHEALTH_PIPELINE_ROOT (weekly Monday 6 AM ET)
  └─> SNOWHEALTH_TASK_FEATURE_ENGINEERING
        ├─> SNOWHEALTH_TASK_TRAIN_XGBOOST  ──┐  (parallel)
        └─> SNOWHEALTH_TASK_TRAIN_LIGHTGBM ──┘
              └─> SNOWHEALTH_TASK_MODEL_EVALUATION (quality gate)
                    └─> SNOWHEALTH_TASK_MODEL_DEPLOYMENT
```

## Project Structure

```
SNOWHEALTH_PIPELINE/
├── manifest.yml                              # DCM project config
├── sources/definitions/
│   └── pipeline.yml                          # Task DAG + code bundle definitions
├── code_bundles/
│   ├── feature_engineering/
│   │   ├── code_bundle.yml                   # Compute config
│   │   └── feature_engineering.py            # 33 features from raw transactions
│   ├── model_training/
│   │   ├── code_bundle.yml
│   │   └── model_training.py                 # XGBoost training + Model Registry
│   ├── model_evaluation/
│   │   ├── code_bundle.yml
│   │   └── model_evaluation.py               # Batch inference + quality gate
│   └── model_deployment/
│       ├── code_bundle.yml
│       └── model_deployment.py               # Promote default + smoke test
└── out/                                      # Compiled output (auto-generated)
```

## Pipeline Steps

| Step | Code Bundle | What It Does |
|------|------------|-------------|
| **1. Feature Engineering** | `feature_engineering.py` | Loads 10K raw transactions, engineers 33 features (calendar, cyclical, lag, rolling, interaction), saves to `SNOWHEALTH_FEATURES.SNOWHEALTH_PIPELINE_FEATURES` |
| **2a. Train XGBoost** | `model_training.py` | Trains XGBoost regressor (300 trees, depth 8), evaluates on holdout, registers to Model Registry with `target_platforms=["WAREHOUSE"]` |
| **2b. Train LightGBM** | `model_training.py` | Runs in parallel with XGBoost for model comparison |
| **3. Evaluate** | `model_evaluation.py` | Batch inference via `mv.run()`, computes MAE/RMSE/R2, enforces quality gate (RMSE < 10.0), saves results for monitoring |
| **4. Deploy** | `model_deployment.py` | Sets default version, runs smoke test (5 predictions), logs deployment status |

---

## Deploy & Run Commands

### Prerequisites

```sql
-- Create the schema and results stage (one-time setup)
CREATE SCHEMA IF NOT EXISTS SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA;
CREATE STAGE IF NOT EXISTS SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_ML_RESULTS_STAGE;
```

### Compile the Pipeline

From the Snowsight Pipeline Builder UI, click **Compile** to validate the YAML and generate the rendered output. Or use the CLI:

```bash
snow dcm compile --project-dir SNOWHEALTH_PIPELINE
```

### Deploy to Snowflake

```bash
# Deploy to the DEV target (defined in manifest.yml)
snow dcm deploy --project-dir SNOWHEALTH_PIPELINE --target DEV
```

This creates:
- 4 code bundles in `SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA`
- 6 tasks forming the DAG (root + 5 pipeline steps)
- All tasks are created in a suspended state

### Resume the Pipeline

```sql
-- Resume the root task to activate the schedule
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_PIPELINE_ROOT RESUME;

-- Or resume all tasks in the DAG
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_TASK_MODEL_DEPLOYMENT RESUME;
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_TASK_MODEL_EVALUATION RESUME;
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_TASK_TRAIN_XGBOOST RESUME;
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_TASK_TRAIN_LIGHTGBM RESUME;
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_TASK_FEATURE_ENGINEERING RESUME;
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_PIPELINE_ROOT RESUME;
```

### Trigger a Manual Run

```sql
-- Execute the root task immediately (does not wait for cron schedule)
EXECUTE TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_PIPELINE_ROOT;
```

### Monitor Pipeline Runs

```sql
-- Check task history
SELECT *
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
    TASK_NAME => 'SNOWHEALTH_PIPELINE_ROOT'
))
ORDER BY SCHEDULED_TIME DESC;

-- Check all pipeline task runs
SELECT NAME, STATE, SCHEDULED_TIME, COMPLETED_TIME, ERROR_MESSAGE
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
))
WHERE NAME LIKE 'SNOWHEALTH_%'
ORDER BY SCHEDULED_TIME DESC;
```

### Suspend the Pipeline

```sql
ALTER TASK SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA.SNOWHEALTH_PIPELINE_ROOT SUSPEND;
```

### Tear Down

```sql
-- Remove all pipeline objects
snow dcm teardown --project-dir SNOWHEALTH_PIPELINE --target DEV
```

---

## MLOps & CI/CD Integration

### Why DCM for ML Pipelines

DCM (Database Change Management) treats ML infrastructure as code. The pipeline definition (`pipeline.yml`), code bundles, and manifest are all version-controlled files that can flow through a standard CI/CD workflow — no manual clicks in the UI to deploy or update models.

### Git-Based Workflow

```
Feature Branch                    Main Branch
─────────────                    ───────────
1. Edit pipeline.yml              4. Merge PR
2. Update .py code bundles        5. CI deploys to PROD
3. Open PR → CI deploys to DEV       └─> snow dcm deploy --target PROD
   └─> snow dcm deploy --target DEV
   └─> Run tests against DEV
```

### Multi-Environment Promotion

Add targets to `manifest.yml` for each environment:

```yaml
targets:
  DEV:
    account_identifier: SFSENORTHAMERICA-TBSMITH_AWS1
    project_name: "SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA_DEV.SNOWHEALTH_PIPELINE"
    project_owner: ML_DEVELOPER_ROLE
  STAGING:
    account_identifier: SFSENORTHAMERICA-TBSMITH_AWS1
    project_name: "SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA_STAGING.SNOWHEALTH_PIPELINE"
    project_owner: ML_ENGINEER_ROLE
  PROD:
    account_identifier: SFSENORTHAMERICA-TBSMITH_AWS1
    project_name: "SNOWHEALTH_ML_DB.SNOWHEALTH_ML_SCHEMA_PROD.SNOWHEALTH_PIPELINE"
    project_owner: ML_OPS_ROLE
```

Deploy to each:

```bash
snow dcm deploy --project-dir SNOWHEALTH_PIPELINE --target DEV
snow dcm deploy --project-dir SNOWHEALTH_PIPELINE --target STAGING
snow dcm deploy --project-dir SNOWHEALTH_PIPELINE --target PROD
```

### CI/CD Pipeline Example (GitHub Actions)

```yaml
name: SnowHealth ML Pipeline CI/CD

on:
  push:
    branches: [main]
    paths: ['SNOWHEALTH_PIPELINE/**']
  pull_request:
    branches: [main]
    paths: ['SNOWHEALTH_PIPELINE/**']

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Snowflake-Labs/snowflake-cli-action@v1
      - run: snow dcm compile --project-dir SNOWHEALTH_PIPELINE

  deploy-dev:
    needs: validate
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Snowflake-Labs/snowflake-cli-action@v1
        with:
          cli-version: latest
      - run: snow dcm deploy --project-dir SNOWHEALTH_PIPELINE --target DEV

  deploy-prod:
    needs: validate
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: Snowflake-Labs/snowflake-cli-action@v1
        with:
          cli-version: latest
      - run: snow dcm deploy --project-dir SNOWHEALTH_PIPELINE --target PROD
```

### MLOps Lifecycle Mapping

| MLOps Concern | How This Pipeline Addresses It |
|---------------|-------------------------------|
| **Reproducibility** | Code bundles are versioned artifacts; same code always produces same model |
| **Automated Retraining** | Weekly cron schedule (Monday 6 AM ET); change to hourly/daily as needed |
| **Quality Gates** | Step 3 enforces RMSE < 10.0 — blocks deployment if threshold breached |
| **Model Versioning** | Each run registers a new version in Snowflake Model Registry |
| **Experiment Tracking** | Training logs params/metrics to `SNOWHEALTH_DEMAND_FORECAST_EXPERIMENT` |
| **Drift Monitoring** | Model Monitor (`SNOWHEALTH_DEMAND_MONITOR`) tracks RMSE/PSI per day with alerting |
| **Rollback** | Model Registry maintains all versions; set `model_ref.default` to roll back |
| **Audit Trail** | Task history + deployment log table + Model Registry lineage |
| **Environment Isolation** | DCM targets (DEV/STAGING/PROD) with separate schemas and roles |
| **Infrastructure as Code** | `pipeline.yml` + `manifest.yml` fully define the pipeline — no manual setup |

### Connecting to Feature Store

The pipeline's feature engineering step writes to `SNOWHEALTH_FEATURES.SNOWHEALTH_PIPELINE_FEATURES`. For the full Feature Store integration with managed Dynamic Tables and online serving, see the interactive notebooks (`02_feature_engineering.ipynb`) which register the Feature View with 10-minute refresh and online serving enabled.

To integrate the Feature Store into the pipeline, replace the feature engineering code bundle with a call to `fs.register_feature_view()` or update the existing Feature View's source table.
