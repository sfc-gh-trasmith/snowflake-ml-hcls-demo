# SnowHealth ML Pipeline

## Overview

A production-ready, automated ML pipeline for retail pharmacy demand forecasting built entirely on Snowflake-native infrastructure. This pipeline demonstrates how to operationalize an end-to-end MLOps workflow using **DCM Projects** (Database Change Management), **Pipeline Builder**, and **Code Bundles** — no external orchestrators, no third-party tools.

The pipeline runs on a weekly cron schedule: it engineers features from raw pharmacy transactions, trains an XGBoost model on compute pools, evaluates against a quality gate, and promotes the winning version to production — all as a single declarative DAG managed as code.

## Key Concepts

### DCM Projects (Database Change Management)

DCM Projects enable infrastructure-as-code for Snowflake. Instead of writing imperative DDL scripts, you declare the desired state of your objects (tasks, code bundles, stages) in YAML definition files. Snowflake compares your definitions against the current state and applies only the necessary changes — similar to Terraform but native to Snowflake.

- **`manifest.yml`** — defines deployment targets (DEV, PROD) and templating variables
- **`sources/definitions/pipeline.yml`** — declares all pipeline objects with `{{ variable }}` placeholders
- **Plan → Deploy workflow** — preview changes before applying with `snow dcm plan`, then `snow dcm deploy`

### Pipeline Builder

The Pipeline Builder is the visual UI in Snowsight for authoring and monitoring task DAGs. The same YAML definitions that power CLI deployments render as an interactive DAG in the UI, giving you a visual representation of your pipeline alongside the code-first workflow.

### Code Bundles

Code Bundles package Python scripts alongside their execution specification (compute type, runtime, dependencies) into a single deployable unit. Each bundle runs as an ML Job on Snowflake compute pools — no containers to manage, no images to build.

- **`type: ml`** — pre-built ML runtime with pandas, scikit-learn, xgboost, snowflake-ml-python
- **`type: custom`** — bring your own `requirements.txt` for custom dependencies
- **`compute_type: compute_pool`** — runs on dedicated CPU/GPU nodes (ML Jobs)
- **`compute_type: warehouse`** — runs on standard Snowflake warehouses

## Pipeline DAG

```
SNOWHEALTH_PIPELINE_ROOT (weekly cron: Monday 6 AM ET)
  └─> SNOWHEALTH_TASK_FEATURE_ENGINEERING
        └─> SNOWHEALTH_TASK_MODEL_TRAINING
              └─> SNOWHEALTH_TASK_MODEL_DEPLOYMENT
SNOWHEALTH_TASK_NOTIFY_COMPLETION (finalizer — runs on success or failure)
```

| Step | Code Bundle | What It Does |
|------|-------------|-------------|
| **Feature Engineering** | `feature_engineering.py` | Loads raw pharmacy transactions, engineers 30+ features (temporal, lag, rolling, interaction), writes to `SNOWHEALTH_PIPELINE_FEATURES` |
| **Model Training** | `model_training.py` | Trains XGBoost regressor, registers versioned model in Snowflake Model Registry as `SNOWHEALTH_PIPELINE_MODEL` with timestamped version |
| **Model Deployment** | `model_deployment.py` | Evaluates on holdout set, enforces RMSE quality gate (< 15.0), promotes to default version, runs smoke test, logs to `SNOWHEALTH_PIPELINE_DEPLOY_LOG` |
| **Finalizer** | SQL task | Logs pipeline completion status to `SNOWHEALTH_PIPELINE_DEPLOY_LOG` — runs regardless of whether the pipeline succeeded or failed |

## Multi-Environment Templating

All environment-specific values are parameterized via Jinja2 templating in `manifest.yml`. The same `pipeline.yml` deploys to any environment without code changes.

| Variable | Default | DEV | PROD |
|----------|---------|-----|------|
| `database` | DEV_SNOWHEALTH_ML_DB | DEV_SNOWHEALTH_ML_DB | PRD_SNOWHEALTH_ML_DB |
| `schema` | SNOWHEALTH_MODELS | SNOWHEALTH_MODELS | SNOWHEALTH_MODELS |
| `warehouse` | COMPUTE_WH | COMPUTE_WH | PROD_ML_WH |
| `compute_pool` | SNOWHEALTH_COMPUTE_POOL | SNOWHEALTH_COMPUTE_POOL | PROD_COMPUTE_POOL |
| `cron_schedule` | Monday 6 AM ET | Monday 6 AM ET | Monday 4 AM ET |
| `model_version` | latest | latest | (override at deploy time) |

### How Variables Reach Python Scripts

Template variables are passed to code bundle scripts via `env_vars` on each task definition:

```
manifest.yml          →  pipeline.yml            →  Python script
(templating variable)     (env_vars on task)         (os.environ)
```

Each code bundle task includes:
```yaml
env_vars:
  - DCM_DATABASE: '{{ database }}'
  - DCM_SCHEMA: '{{ schema }}'
```

At deploy time, `{{ database }}` resolves to `DEV_SNOWHEALTH_ML_DB` (or `PRD_SNOWHEALTH_ML_DB` for PROD). The Python scripts read these at runtime:
```python
DB = os.environ.get("DCM_DATABASE", "DEV_SNOWHEALTH_ML_DB")
SCHEMA = os.environ.get("DCM_SCHEMA", "SNOWHEALTH_MODELS")
```

This means **zero hardcoded database references** in Python — the same code runs in any environment.

## Model Version Control

The pipeline supports two deployment modes via the `model_version` template variable:

### Auto Mode (DEV default)

Training produces a new timestamped version each run. The deployment step auto-selects the latest, evaluates it, and promotes if it passes the quality gate.

```bash
snow dcm deploy --from pipeline --target DEV
# model_version defaults to "latest"
# Pipeline trains → evaluates → promotes newest version automatically
```

### Pinned Mode (PROD)

A human reviews DEV results and pins a known-good version for production deployment. The quality gate still runs — a pinned version that fails RMSE is rejected.

```bash
snow dcm deploy --from pipeline --target PROD \
  --variable model_version=PIPELINE_20261012_v3
```

The variable flows through as:
```
CLI --variable → manifest templating → {{ model_version }} in pipeline.yml
  → env_vars: MODEL_VERSION on the task → os.environ in Python
```

## Project Structure

```
pipeline/
├── manifest.yml                              # DCM config, targets, templating variables
├── README.md                                 # This file
├── sources/
│   └── definitions/
│       └── pipeline.yml                      # Templatized pipeline DAG + finalizer
├── code_bundles/
│   ├── feature_engineering/
│   │   ├── code_bundle.yml                   # ml + compute_pool spec
│   │   └── feature_engineering.py            # 30+ features (reads DCM_DATABASE env var)
│   ├── model_training/
│   │   ├── code_bundle.yml                   # ml + compute_pool spec
│   │   └── model_training.py                 # XGBoost → Model Registry (reads DCM_DATABASE)
│   └── model_deployment/
│       ├── code_bundle.yml                   # ml + compute_pool spec
│       └── model_deployment.py               # Quality gate → promote (reads DCM_DATABASE + MODEL_VERSION)
└── out/                                      # Generated by plan/deploy (gitignored)
```

## Deploy & Run

### Prerequisites

- Snowflake account with `ACCOUNTADMIN` or equivalent role
- Compute pool created: `SNOWHEALTH_COMPUTE_POOL` (CPU_X64_S, 1-5 nodes)

### Option A: Deploy from a Snowflake Workspace (no CLI needed)

The `07_ml_pipeline.ipynb` notebook handles everything — create, deploy, execute, validate, suspend — using SQL:

```sql
-- Create the DCM project and results stage
CREATE DCM PROJECT IF NOT EXISTS DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE;
CREATE STAGE IF NOT EXISTS DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_RESULTS;

-- Deploy directly from the workspace stage
EXECUTE DCM PROJECT DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE
    DEPLOY
    USING CONFIGURATION DEV
    FROM 'snow://workspace/USER$.PUBLIC."snowflake-ml-hcls-demo"/versions/live/pipeline';
```

### Option B: Deploy from CLI

```bash
# Update account_identifier in manifest.yml first, then:
snow dcm deploy --from pipeline --target DEV

# Preview changes without applying:
snow dcm plan --from pipeline --target DEV
```

### Execute

```sql
-- Resume the task DAG (leaf first, root last)
ALTER TASK DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_TASK_MODEL_DEPLOYMENT RESUME;
ALTER TASK DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_TASK_MODEL_TRAINING RESUME;
ALTER TASK DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_TASK_FEATURE_ENGINEERING RESUME;
ALTER TASK DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_ROOT RESUME;

-- Trigger an immediate run
EXECUTE TASK DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_ROOT;

-- Monitor execution
SELECT NAME, STATE, SCHEDULED_TIME, COMPLETED_TIME
FROM TABLE(DEV_SNOWHEALTH_ML_DB.INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -1, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 10
))
WHERE NAME LIKE 'SNOWHEALTH%'
ORDER BY SCHEDULED_TIME DESC;
```

### Suspend

```sql
ALTER TASK DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE_ROOT SUSPEND;
```

### Teardown

```bash
snow dcm teardown --from pipeline --target DEV
```

Or via SQL:
```sql
EXECUTE DCM PROJECT DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE PURGE;
DROP DCM PROJECT DEV_SNOWHEALTH_ML_DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE;
```

## Git Workflow

In a CI/CD setup, the pipeline definition lives in Git and deploys automatically:

| Branch | Action | Target |
|--------|--------|--------|
| `feature/*` | `snow dcm plan` (preview only) | DEV |
| `develop` | `snow dcm deploy` on merge | DEV |
| `main` | `snow dcm deploy --variable model_version=<pinned>` on merge | PROD |

Version tracking spans three layers:

- **Pipeline code** — Git commits (SHA tracks every change to definitions and bundles)
- **DCM deployments** — Snowflake stores immutable deployment artifacts per version
- **Model artifacts** — Snowflake Model Registry tracks every trained version

## Quality Gate

The deployment step enforces a quality gate before any model reaches production:

1. Evaluate on 20% holdout set (MAE, RMSE, R2)
2. RMSE must be < 15.0 (configurable threshold)
3. If passed → set as default version + smoke test
4. If failed → `ValueError` raised, task fails, previous default stays live
5. All results logged to `SNOWHEALTH_PIPELINE_DEPLOY_LOG`
6. Finalizer task logs overall pipeline status regardless of outcome
