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

## What the template demonstrates

| Concern | How it's handled |
|---|---|
| Infrastructure as code | DCM project (`snow dcm plan` / `deploy`): code bundles, task DAG, schedules |
| Features as code | Declarative Feature Store (`snow feature plan` / `apply`): entity, batch source, feature view |
| Orchestration | Snowflake task graph, authored in Pipeline Builder YAML |
| Training / promotion | Code bundles on a compute pool (ML Jobs) + Model Registry + quality gate |
| Multi-environment | One set of definitions, Jinja templating per target (`DEV`, `PROD`) |
| CI/CD | PR → plan; merge → deploy + run DEV, then promote to PROD |
| Auth & isolation | OIDC per GitHub environment → dedicated service user + deployer role per env |

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

The pipeline (task graph) per environment:

```
MLOPS_PIPELINE_ROOT (cron)
  └─> MLOPS_TASK_FEATURE_ENGINEERING     code bundle → writes the feature source table
        └─> MLOPS_TASK_FEATURE_STORE_REFRESH  refreshes the feature view
              └─> MLOPS_TASK_MODEL_TRAINING   point-in-time training set → Model Registry
                    └─> MLOPS_TASK_MODEL_DEPLOYMENT  quality gate → promote default version
MLOPS_TASK_NOTIFY_COMPLETION (finalizer)
```

## Repository layout

```
├── .github/workflows/
│   ├── ci.yml                 PR → plan DEV
│   ├── deploy.yml             main → deploy + run DEV → deploy + run PROD
│   └── _deploy-env.yml        reusable per-environment job (OIDC, CLI setup)
├── resources/                 deployable projects
│   ├── feature_store/         declarative Feature Store (snow feature)
│   └── pipeline/              DCM project: pipeline.yml + code_bundles/
├── scripts/
│   ├── deploy_env.sh          bootstrap → feature apply → dcm deploy (plan|deploy)
│   ├── run_pipeline.sh        run the task graph once + validate
│   ├── bootstrap_env.sql      per-env objects DCM doesn't manage
│   ├── setup_cicd.sql         one-time admin: DBs, compute pool, roles, OIDC users
│   └── seed_data.py           one-time admin: synthetic source data per env
├── notebooks/                 optional interactive walkthrough of Snowflake ML features
├── source/                    shared Python for the notebooks (and the sample data)
└── docs/docs.html             detailed documentation
```

## Quick start

**1. One-time setup (admin).** Edit the two OIDC `SUBJECT` values in
`scripts/setup_cicd.sql` for your repo
(`gh api repos/<owner>/<repo>/actions/oidc/customization/sub`), then:

```bash
snow sql -f scripts/setup_cicd.sql -c <admin_connection>
python scripts/seed_data.py --env DEV  --connection <admin_connection>
python scripts/seed_data.py --env PROD --connection <admin_connection>

gh api -X PUT repos/<owner>/<repo>/environments/dev
gh api -X PUT repos/<owner>/<repo>/environments/prod
gh variable set SNOWFLAKE_ACCOUNT --body "<ORG>-<ACCOUNT>"
```

**2. First deploy of DEV** (so PR plans have something to diff against). Uses
a named connection, so your cached login is reused:

```bash
SNOWFLAKE_CONNECTION=<name> SNOWFLAKE_ROLE=MLOPS_DEV_DEPLOYER \
SNOWFLAKE_ACCOUNT=<ORG>-<ACCOUNT> scripts/deploy_env.sh DEV deploy
```

`snow feature` needs `snowflake-ml-python[feature_store]` in the same
interpreter as the Snowflake CLI, for example:
`uv tool install snowflake-cli --with "snowflake-ml-python[feature_store]"`.

**3. Work through Git.** Open a PR: `ci.yml` plans DEV. Merge: `deploy.yml`
deploys and runs DEV, then promotes to PROD. Add required reviewers to the
`prod` environment to gate promotion behind approval.

## Adapting the template

| To change… | Edit |
|---|---|
| Source data | `RAW` tables (ingestion) + the source query in `resources/feature_store/sources/datasources/` |
| Features | `resources/pipeline/code_bundles/feature_engineering/` + the feature view YAML (breaking change → new `version`) |
| Model / training | `resources/pipeline/code_bundles/model_training/` |
| Promotion rule | `resources/pipeline/code_bundles/model_deployment/` (quality gate) |
| Schedule, warehouse, pool, names | `templating` in `resources/*/manifest.yml` |
| Environments | `targets` in both manifests + GitHub environments + `setup_cicd.sql` |

## Notebooks (optional)

`notebooks/01`–`07` are an interactive tour of the underlying Snowflake ML
features (Feature Store, Experiment Tracking, Tuner, batch / real-time inference,
Model Monitor) against `DEV_MLOPS_DB`. They aren't needed for the DCM workflow;
`07_ml_pipeline` shows deploying the same DCM project from a Snowflake workspace.
