# Deploying the MLOps Pipeline

This folder holds the two deployable projects. They're deployed together, in a
fixed order, by one script (`scripts/deploy_env.sh`). You don't run them
independently.

| Project | Tool | Owns | Lands in |
|---|---|---|---|
| [`feature_store/`](feature_store) | Declarative Feature Store (`snow feature plan` / `apply`) | *What the features are*: entity, batch source, feature view | `<ENV>_MLOPS_DB.FEATURE_STORE` |
| [`pipeline/`](pipeline) | DCM project (`snow dcm plan` / `deploy`) | *How they're computed and used*: code bundles, task DAG, schedule | `<ENV>_MLOPS_DB.MODELS` |

> Only `pipeline/` is a DCM project. `feature_store/` uses the Feature Store's
> own declarative workflow. Both follow the same plan → apply model, and both
> use `targets` / `templating` in a `manifest.yml` for DEV and PROD.

## Deployment order

```
1. bootstrap_env.sql      DCM project object, results stage, deploy log,
                          empty MODELS.MLOPS_PIPELINE_FEATURES table
2. feature_store/         snow feature init → plan → apply
3. pipeline/              snow dcm plan → deploy
4. run_pipeline.sh        (optional) run the DAG once and validate
```

**Why the Feature Store goes first:** the pipeline's refresh, training and
deployment tasks read from the feature view `MLOPS_PIPELINE_FV/V1`. That view
must exist before the DAG runs. The view itself reads from
`MODELS.MLOPS_PIPELINE_FEATURES`, so step 1 creates that table empty, and the
pipeline's feature-engineering task fills it on every run.

At runtime the two projects connect like this:

```
FEATURE_ENGINEERING   ─writes→      MODELS.MLOPS_PIPELINE_FEATURES       (batch source)
FEATURE_STORE_REFRESH ─refreshes→   FEATURE_STORE.MLOPS_PIPELINE_FV$V1   (dynamic table)
MODEL_TRAINING / MODEL_DEPLOYMENT ─generate_training_set(spine, [FV])→ features + label
```

## Prerequisites

- One-time admin setup done: `scripts/setup_cicd.sql` (databases, compute pool,
  deployer roles, OIDC service users) and `scripts/seed_data.py` per environment.
  See the [root README](../README.md#quick-start).
- Snowflake CLI with the Feature Store extra **in the same interpreter**:
  ```bash
  uv tool install snowflake-cli --with "snowflake-ml-python[feature_store]"
  ```
- `jq` (used by `run_pipeline.sh`).

## Deploy

### Via Git (normal path)

| Event | Workflow | DEV | PROD |
|---|---|---|---|
| PR → `main` | `ci.yml` | `deploy_env.sh DEV plan` (feature + DCM plans, read-only) | — |
| Merge to `main` | `deploy.yml` | `deploy_env.sh DEV deploy` + `run_pipeline.sh DEV` | same for PROD, only after DEV passes |

Add required reviewers to the `prod` GitHub environment to gate promotion.

### Locally (first deploy, or debugging)

```bash
export SNOWFLAKE_CONNECTION=<name> SNOWFLAKE_ROLE=MLOPS_DEV_DEPLOYER
export SNOWFLAKE_ACCOUNT=<ORG>-<ACCOUNT>

scripts/deploy_env.sh DEV plan     # preview both projects, changes nothing
scripts/deploy_env.sh DEV deploy   # steps 1–3
scripts/run_pipeline.sh DEV        # step 4: run once, wait, validate, re-suspend
```

`deploy_env.sh` works on a temp copy and fills the `<YOUR_ORG>-<YOUR_ACCOUNT>`
placeholder in both manifests from `SNOWFLAKE_ACCOUNT`, so the checkout stays
generic.

<details>
<summary>What the script runs, step by step (manual equivalent)</summary>

```bash
# 1. Bootstrap
snow sql -f scripts/bootstrap_env.sql -D "db=DEV_MLOPS_DB" -c <conn>

# 2. Feature Store (run from the project dir; account placeholder filled in)
cd resources/feature_store
snow feature init  --yaml --target DEV -c <conn>  # first time only; exports into sources/, so use a scratch copy
snow feature plan  --target DEV -c <conn>
snow feature apply --target DEV -c <conn>         # no --destructive: breaking changes go to a new FV version

# 3. Pipeline (DCM)
cd ../pipeline
snow dcm plan   DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE --target DEV -c <conn>
snow dcm deploy DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE --target DEV --alias <alias> -c <conn>
```
</details>

## What gets deployed

### Pipeline DAG (`pipeline/sources/definitions/pipeline.yml`)

```
MLOPS_PIPELINE_ROOT (cron: Mon 6 AM ET DEV / 4 AM ET PROD)
  └─> MLOPS_TASK_FEATURE_ENGINEERING
        └─> MLOPS_TASK_FEATURE_STORE_REFRESH
              └─> MLOPS_TASK_MODEL_TRAINING
                    └─> MLOPS_TASK_MODEL_DEPLOYMENT
MLOPS_TASK_NOTIFY_COMPLETION (finalizer: runs on success or failure)
```

| Step | Runs | What it does |
|---|---|---|
| Feature engineering | `code_bundles/feature_engineering` (ML Job) | Raw transactions → 30+ features, written to `MODELS.MLOPS_PIPELINE_FEATURES` (`mode("truncate")`) |
| Feature store refresh | SQL task | Refreshes `FEATURE_STORE.MLOPS_PIPELINE_FV$V1` |
| Model training | `code_bundles/model_training` (ML Job) | Point-in-time training set from the FV → XGBoost → Model Registry (`MLOPS_PIPELINE_MODEL`, timestamped version) |
| Model deployment | `code_bundles/model_deployment` (ML Job) | Holdout eval, RMSE gate (< 15.0), promote to default, smoke test, write `MLOPS_PIPELINE_DEPLOY_LOG` |
| Finalizer | SQL task | Logs overall pipeline status |

Code bundles package a script with its runtime spec (`type: ml`, `compute_type:
compute_pool`) and run as ML Jobs on `MLOPS_COMPUTE_POOL`. There are no images
to build.

### Feature Store (`feature_store/sources/`)

```
entities/MLOPS_TRANSACTION.yaml                   join key: TRANSACTION_ID
datasources/MLOPS_PIPELINE_FEATURES_SRC.yaml      query over MODELS.MLOPS_PIPELINE_FEATURES
feature_views/MLOPS_PIPELINE_FV.yaml              BatchFeatureView V1 (dynamic table)
```

- **Entity grain is `TRANSACTION_ID`.** (SKU, store, date) isn't unique in this
  data, so a SKU-store entity would give a wrong point-in-time join.
- **The batch source uses an explicit `query`.** `columns:` alone doesn't
  filter, and without the query the label `UNITS_SOLD` would leak into the
  feature view.

## Environments and templating

Both manifests map `DEV` / `PROD` targets to their own database and deployer
role. Definitions use `{{ variable }}` placeholders.

| Variable (`pipeline/manifest.yml`) | DEV | PROD |
|---|---|---|
| `database` | `DEV_MLOPS_DB` | `PRD_MLOPS_DB` |
| `schema` | `MODELS` | `MODELS` |
| `warehouse` / `compute_pool` | `COMPUTE_WH` / `MLOPS_COMPUTE_POOL` | same (shared) |
| `cron_schedule` | Mon 6 AM ET | Mon 4 AM ET |
| `model_version` | `latest` | `latest` (override to pin) |
| `fs_schema` / `fv_name` / `fv_version` | `FEATURE_STORE` / `MLOPS_PIPELINE_FV` / `V1` | same |

Values reach Python through `env_vars` on each task:

```
manifest.yml templating → {{ var }} in pipeline.yml → env_vars on task → os.environ in the bundle
```

So the code bundles contain no hardcoded database names.

**Pinning a model in PROD:** by default deployment promotes the newest trained
version. To pin a reviewed version, pass `--variable model_version=<VERSION>`
to `snow dcm deploy`. The quality gate still runs, and a pinned version that
fails it is rejected.

## Common changes

| Change | Edit | Notes |
|---|---|---|
| Add or modify a feature | `pipeline/code_bundles/feature_engineering/` + `feature_store/sources/datasources/` query + bootstrap table columns | Breaking change → publish `MLOPS_PIPELINE_FV` **V2** and bump `fv_version`. V1 keeps serving until the pipeline is redeployed |
| Change model / training | `pipeline/code_bundles/model_training/` | |
| Change promotion rule | `pipeline/code_bundles/model_deployment/` | |
| Schedule, warehouse, pool | `templating` in `pipeline/manifest.yml` | |
| Add an environment | `targets` in **both** manifests, `setup_cicd.sql`, `deploy_env.sh` / `run_pipeline.sh` case blocks, GitHub environment | |

## Operate

```sql
-- Run once now (or use scripts/run_pipeline.sh, which also validates)
SELECT SYSTEM$TASK_DEPENDENTS_ENABLE('DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE_ROOT');
EXECUTE TASK DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE_ROOT;

-- Monitor
SELECT NAME, STATE, SCHEDULED_TIME, COMPLETED_TIME, ERROR_MESSAGE
FROM TABLE(DEV_MLOPS_DB.INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -2, CURRENT_TIMESTAMP())))
WHERE NAME LIKE 'MLOPS%'
ORDER BY SCHEDULED_TIME DESC;

-- Stop the weekly schedule
ALTER TASK DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE_ROOT SUSPEND;
```

Teardown, pipeline first (it depends on the feature view):

```sql
EXECUTE DCM PROJECT DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE PURGE;
DROP DCM PROJECT DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE;
DROP SCHEMA DEV_MLOPS_DB.FEATURE_STORE;   -- feature store objects
```

## Alternative: deploy from a Snowflake Workspace

`notebooks/07_ml_pipeline.ipynb` deploys the DCM project with SQL
(`EXECUTE DCM PROJECT … DEPLOY FROM 'snow://workspace/…'`) without the CLI. It
covers the pipeline only, so deploy the Feature Store first (CLI step 2 above).
