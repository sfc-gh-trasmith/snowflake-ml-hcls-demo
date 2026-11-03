# MLOps with DCM on Snowflake

ML pipelines on Snowflake tend to grow out of notebooks and one-off scripts:
feature definitions get copied between environments, tasks are edited by hand,
and nobody can say what is actually running in PROD. This **template** makes
features, training pipelines and promotion declarative. **DCM projects** and
the **declarative Feature Store** turn every change into a reviewable plan,
then apply that same plan to DEV and PROD through **GitHub Actions** (OIDC, no
secrets).

The bundled model (an XGBoost regressor on synthetic transaction data) is a
placeholder. Swap in your own data, features and training code; the deployment
pattern stays the same.

> Full documentation: [here](https://sfc-gh-trasmith.github.io/snowflake-mlops-dcm/docs.html)

## How it fits together

There are two deployable projects under `resources/`. They're always deployed
together, in a fixed order, by one script (`scripts/deploy_env.sh`):

| Project | Tool | Owns | Lands in |
|---|---|---|---|
| [`feature_store/`](resources/feature_store) | Declarative Feature Store (`snow feature plan` / `apply`) | *What the features are*: entity, batch source, feature view | `<ENV>_MLOPS_DB.FEATURE_STORE` |
| [`pipeline/`](resources/pipeline) | DCM project (`snow dcm plan` / `deploy`) | *How they're computed and used*: code bundles, task DAG, schedule | `<ENV>_MLOPS_DB.MODELS` |

> Only `pipeline/` is a DCM project. `feature_store/` uses the Feature Store's
> own declarative workflow. Both follow plan → apply and map `DEV` / `PROD`
> targets in a `manifest.yml`.

**Deployment order** (what `deploy_env.sh <ENV> deploy` runs):

```
1. bootstrap_env.sql   DCM project object, results stage, deploy log,
                       empty MODELS.MLOPS_PIPELINE_FEATURES table
2. feature_store/      snow feature init → plan → apply
3. pipeline/           snow dcm plan → deploy
4. run_pipeline.sh     (separate script) run the DAG once and validate
```

The Feature Store goes first because the pipeline's tasks read the feature
view `MLOPS_PIPELINE_FV/V1`. The view in turn reads
`MODELS.MLOPS_PIPELINE_FEATURES`, which step 1 creates empty and the pipeline
fills on every run:

```
FEATURE_ENGINEERING   ─writes→      MODELS.MLOPS_PIPELINE_FEATURES       (batch source)
FEATURE_STORE_REFRESH ─refreshes→   FEATURE_STORE.MLOPS_PIPELINE_FV$V1   (dynamic table)
MODEL_TRAINING / MODEL_DEPLOYMENT ─generate_training_set(spine, [FV])→ features + label
```

## Architecture

```
            GitHub                                     Snowflake (single account)
 ┌──────────────────────────┐            ┌────────────────────────────────────────────┐
 │ PR ──► ci.yml (plan DEV) │──OIDC dev─►│ SVC_MLOPS_GH_DEV  → MLOPS_DEV_DEPLOYER     │
 │                          │            │   DEV_MLOPS_DB   (dev data)                │
 │ main ──► deploy.yml      │            │                                            │
 │   ├─ dev   (deploy+run)  │──OIDC prod►│ SVC_MLOPS_GH_PROD → MLOPS_PROD_DEPLOYER    │
 │   └─ prod  (needs dev)   │            │   PRD_MLOPS_DB   (prod data)               │
 └──────────────────────────┘            │ shared: COMPUTE_WH, MLOPS_COMPUTE_POOL     │
                                         └────────────────────────────────────────────┘
```

Each environment database has the same layout:

```
<ENV>_MLOPS_DB
├── RAW             source data (owned by ingestion, never written by CI)
├── FEATURE_STORE   declarative feature store: entity, feature view (dynamic table)
└── MODELS          DCM project, code bundles, task DAG, model registry, deploy log
```

## Deploy

### Prerequisites

- Snowflake CLI with the Feature Store extra **in the same interpreter**:
  `uv tool install snowflake-cli --with "snowflake-ml-python[feature_store]"`
- `gh` and `jq`.

### 1. One-time setup (admin)

Set the two OIDC `SUBJECT` values in `scripts/setup_cicd.sql` for your repo
(format and lookup command are in the file), then:

```bash
snow sql -f scripts/setup_cicd.sql -c <admin_connection>
python scripts/seed_data.py --env DEV  --connection <admin_connection>
python scripts/seed_data.py --env PROD --connection <admin_connection>

gh api -X PUT repos/<owner>/<repo>/environments/dev
gh api -X PUT repos/<owner>/<repo>/environments/prod
gh variable set SNOWFLAKE_ACCOUNT --body "<ORG>-<ACCOUNT>"
```

### 2. First deploy of DEV

So PR plans have something to diff against. This uses a named connection, so
your cached login is reused:

```bash
export SNOWFLAKE_CONNECTION=<name> SNOWFLAKE_ROLE=MLOPS_DEV_DEPLOYER
export SNOWFLAKE_ACCOUNT=<ORG>-<ACCOUNT>

scripts/deploy_env.sh DEV plan     # preview both projects, changes nothing
scripts/deploy_env.sh DEV deploy   # steps 1–3
scripts/run_pipeline.sh DEV        # run once, wait, validate, re-suspend
```

`deploy_env.sh` works on a temp copy and fills the `<YOUR_ORG>-<YOUR_ACCOUNT>`
placeholder in both manifests from `SNOWFLAKE_ACCOUNT`, so the checkout stays
generic.

<details>
<summary>Manual equivalent of deploy_env.sh</summary>

```bash
# 1. Bootstrap
snow sql -f scripts/bootstrap_env.sql -D "db=DEV_MLOPS_DB" -c <conn>

# 2. Feature Store (from a copy with the account placeholder filled in)
cd resources/feature_store
snow feature init  --yaml --target DEV -c <conn>  # exports into sources/, so run it in a scratch copy
snow feature plan  --target DEV -c <conn>
snow feature apply --target DEV -c <conn>         # no --destructive: breaking changes go to a new FV version

# 3. Pipeline (DCM)
cd ../pipeline
snow dcm plan   DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE --target DEV -c <conn>
snow dcm deploy DEV_MLOPS_DB.MODELS.MLOPS_PIPELINE --target DEV --alias <alias> -c <conn>
```
</details>

### 3. Work through Git

| Event | Workflow | DEV | PROD |
|---|---|---|---|
| PR → `main` | `ci.yml` | `deploy_env.sh DEV plan` (feature + DCM plans, read-only) | — |
| Merge to `main` | `deploy.yml` | `deploy_env.sh DEV deploy` + `run_pipeline.sh DEV` | same, only after DEV passes |

Add required reviewers to the `prod` GitHub environment to gate promotion
behind approval.

## What gets deployed

### Pipeline DAG (`resources/pipeline/sources/definitions/pipeline.yml`)

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
to build. If the quality gate fails, the task fails and the previous default
model version stays live.

### Feature Store (`resources/feature_store/sources/`)

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

### Environments and templating

Definitions use `{{ variable }}` placeholders, resolved per target from
`templating` in each `manifest.yml`:

| Variable (`resources/pipeline/manifest.yml`) | DEV | PROD |
|---|---|---|
| `database` / `schema` | `DEV_MLOPS_DB` / `MODELS` | `PRD_MLOPS_DB` / `MODELS` |
| `warehouse` / `compute_pool` | `COMPUTE_WH` / `MLOPS_COMPUTE_POOL` | same (shared) |
| `cron_schedule` | Mon 6 AM ET | Mon 4 AM ET |
| `model_version` | `latest` | `latest` (override to pin) |
| `fs_schema` / `fv_name` / `fv_version` | `FEATURE_STORE` / `MLOPS_PIPELINE_FV` / `V1` | same |

Values reach Python through `env_vars` on each task (`manifest.yml` →
`{{ var }}` in `pipeline.yml` → `os.environ` in the bundle), so the code
bundles contain no hardcoded database names.

**Pinning a model in PROD:** by default deployment promotes the newest trained
version. To pin a reviewed version, pass `--variable model_version=<VERSION>`
to `snow dcm deploy`. The quality gate still runs, and a pinned version that
fails it is rejected.

## Adapting the template

| To change… | Edit | Notes |
|---|---|---|
| Source data | `RAW` tables (ingestion) + the source query in `resources/feature_store/sources/datasources/` | |
| Features | `resources/pipeline/code_bundles/feature_engineering/` + datasource query + feature table in `scripts/bootstrap_env.sql` | Breaking change → publish `MLOPS_PIPELINE_FV` **V2** and bump `fv_version`. V1 keeps serving until the pipeline is redeployed |
| Model / training | `resources/pipeline/code_bundles/model_training/` | |
| Promotion rule | `resources/pipeline/code_bundles/model_deployment/` (quality gate) | |
| Schedule, warehouse, pool, names | `templating` in `resources/*/manifest.yml` | |
| Environments | `targets` in **both** manifests, `setup_cicd.sql`, the case blocks in `deploy_env.sh` / `run_pipeline.sh`, GitHub environments | |

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
DROP SCHEMA DEV_MLOPS_DB.FEATURE_STORE;   -- drops all feature store objects
```

## Repository layout

```
├── .github/workflows/
│   ├── ci.yml                 PR → plan DEV
│   ├── deploy.yml             main → deploy + run DEV → deploy + run PROD
│   └── _deploy-env.yml        reusable per-environment job (OIDC, CLI setup)
├── resources/
│   ├── feature_store/         declarative Feature Store (snow feature)
│   └── pipeline/              DCM project: manifest.yml, sources/definitions/pipeline.yml, code_bundles/
├── scripts/
│   ├── deploy_env.sh          bootstrap → feature apply → dcm deploy (plan|deploy)
│   ├── run_pipeline.sh        run the task graph once + validate
│   ├── bootstrap_env.sql      per-env objects neither project manages
│   ├── setup_cicd.sql         one-time admin: DBs, compute pool, roles, OIDC users
│   └── seed_data.py           one-time admin: synthetic source data per env
├── notebooks/                 optional interactive walkthrough of Snowflake ML features
├── source/                    shared Python for the notebooks (and the sample data)
└── docs/docs.html             detailed documentation
```

## Notebooks (optional)

`notebooks/01`–`07` are an interactive tour of the underlying Snowflake ML
features (Feature Store, Experiment Tracking, Tuner, batch / real-time
inference, Model Monitor) against `DEV_MLOPS_DB`. They aren't needed for the
DCM workflow. `07_ml_pipeline` deploys the DCM project from a Snowflake
workspace with SQL (`EXECUTE DCM PROJECT … DEPLOY FROM 'snow://workspace/…'`).
It covers the pipeline only, so deploy the Feature Store first.
