# SnowHealth Demand Forecasting — ML Solution

## Overview

End-to-end machine learning solution for retail pharmacy demand forecasting built entirely on **Snowflake ML**. Predicts units sold per SKU-store combination using XGBoost, covering the full ML lifecycle: data ingestion, feature engineering, model training, hyperparameter tuning, batch and real-time inference, model explainability, and drift monitoring.

## Business Use Cases

| Use Case | How This Solution Helps |
|----------|------------------------|
| **Inventory Replenishment** | Predict units sold per SKU-store to optimize reorder points and safety stock |
| **Medication Purchasing** | Forecast prescription drug demand to negotiate volume contracts with suppliers |
| **Store & Fulfillment Planning** | Model demand by channel (in-store, online, drive-thru) for staffing |
| **Distribution** | Regional demand forecasts to optimize DC-to-store allocation |
| **Workforce Scheduling** | Predict service demand (flu shots, COVID tests) for pharmacy staff scheduling |

## Architecture

```
SNOWHEALTH_ML_DB (Database)
├── SNOWHEALTH_RAW (Schema)              Raw transaction data
│   └── SNOWHEALTH_DEMAND_TRANSACTIONS   10,000 synthetic transactions
│
├── SNOWHEALTH_FEATURES (Schema)         Feature Store
│   ├── SNOWHEALTH_DEMAND_FEATURES       Engineered feature table (change tracking)
│   ├── SNOWHEALTH_SKU_STORE             Entity (join keys: SKU_ID, STORE_ID)
│   └── SNOWHEALTH_DEMAND_FV/V01         Managed Feature View (DT, 10-min refresh)
│                                        Postgres-backed online serving (1-min lag)
│
├── SNOWHEALTH_MODELS (Schema)           Model Registry, Inference & Monitoring
│   ├── SNOWHEALTH_DEMAND_FORECAST       Model (BASELINE_V1, TUNED_V1 [default])
│   ├── SNOWHEALTH_DEMAND_PREDICTIONS    Predictions table (source for monitor)
│   ├── SNOWHEALTH_MONITOR_BASELINE      Baseline snapshot for drift comparison
│   ├── SNOWHEALTH_DEMAND_MONITOR        Model Version Monitor (PSI, Wasserstein)
│   ├── SNOWHEALTH_CHAMPION_SVC          SPCS inference service (BASELINE_V1)
│   ├── SNOWHEALTH_CHALLENGER_SVC        SPCS inference service (TUNED_V1)
│   └── SNOWHEALTH_GATEWAY              Traffic-split gateway (90/10)
│
└── SNOWHEALTH_COMPUTE_POOL              CPU_X64_S, 1-5 nodes (ML Jobs + serving)
```

## Project Structure

```
├── source/
│   ├── config.py                  Central config: DB names, model params, feature lists
│   ├── synthetic_data.py          Generates 10K synthetic retail pharmacy transactions
│   ├── feature_engineering.py     Feature transforms: calendar, cyclical, lag, interaction
│   └── model_utils.py            Training, evaluation, comparison, SHAP helpers
│
├── notebooks/
│   ├── 01_setup.ipynb             Infrastructure setup & data exploration
│   ├── 02_feature_engineer.ipynb  Feature engineering & Postgres-backed online Feature Store
│   ├── 03_model_train.ipynb       XGBoost + LightGBM with Experiment Tracking
│   ├── 04_model_tune.ipynb        Snowflake ML Tuner (Ray on SPCS compute pool)
│   ├── 05_inference.ipynb         Batch + champion/challenger + SHAP explainability
│   ├── 06_model_monitor.ipynb     Drift detection with Model Version Monitor
│   └── 07_ml_pipeline.ipynb       Pipeline Builder + Code Bundles + DCM demo
│
├── pipeline/                      DCM project — Pipeline Builder + Code Bundles
│   ├── manifest.yml               Project config (target, owner)
│   ├── sources/definitions/
│   │   └── pipeline.yml           3 code bundles + 4 tasks (DAG)
│   └── code_bundles/              feature_engineering, model_training, model_deployment
└── README.md
```

## Notebooks

### 01_setup — Infrastructure & Data
- Creates `SNOWHEALTH_ML_DB` database with 3 schemas
- Creates `SNOWHEALTH_COMPUTE_POOL` (CPU_X64_S, 1-5 nodes, auto-resume)
- Generates and loads 10K synthetic pharmacy transactions
- Data exploration visualizations

### 02_feature_engineer — Feature Store
- Calendar, cyclical (sin/cos), lag (7/14/30d), rolling average, and interaction features
- Registers **Entity** (`SKU_ID`, `STORE_ID`) and **managed Feature View** (Dynamic Table, 10-min refresh)
- Enables **Postgres-backed online serving** (`OnlineStoreType.POSTGRES`, 1-min target lag)
- Verifies Feature Store lineage

### 03_model_train — Experiment Tracking & Model Registry
- Trains XGBoost and LightGBM regressors
- **Snowflake Experiment Tracking**: logs params, metrics, feature importance per run
- Registers best model as `BASELINE_V1` in Model Registry
- Feature importance visualization and model comparison

### 04_model_tune — Snowflake ML Tuner
- **Snowflake ML Tuner API** (Ray Tune on SPCS) — not sklearn
- RandomSearch, 10 trials on `SNOWHEALTH_COMPUTE_POOL`
- Best trial registered as `TUNED_V1`, set as default version
- Self-contained `train_func` for remote Ray workers

### 05_inference — Batch, Real-Time & Explainability
- **Part A**: Warehouse batch `mv.run()` on features table
- **Part B**: SPCS batch `mv.run_batch()` — 1M rows, 3 replicas on compute pool
- **Part C**: Champion/Challenger deployment
  - Two SPCS services with `feature_sources_per_function` (Postgres online store)
  - Traffic-split gateway: 90% champion (`BASELINE_V1`) / 10% challenger (`TUNED_V1`)
  - Entity-ID-only REST payloads (sub-100ms production latency)
  - Auto-Capture enabled on both services
- **Part D**: SHAP explainability — `mv.run(function_name="explain")`, force plot, violin plot

### 06_model_monitor — Drift Detection
- Creates baseline snapshot from current predictions
- Simulates drift: TEMPERATURE_F +15°F, INVENTORY_ON_HAND -40%, FLU_INDEX ×2
- `CREATE MODEL MONITOR` with baseline comparison (regression task)
- Queries drift metrics: **PSI**, **Difference of Means**, **Wasserstein Distance**
- Consolidated drift summary with alert thresholds

### 07_ml_pipeline — Pipeline Builder & Code Bundles
- Lightweight companion to the interactive notebooks — demonstrates the **production MLOps** path
- Explains **Pipeline Builder** (visual DAG designer), **Code Bundles** (packaged Python jobs), and **DCM** (infrastructure-as-code)
- Deploys, executes, and validates the `SNOWHEALTH_PIPELINE` DCM project
- Validates outputs: feature table (10K rows), model version in registry, deploy log with RMSE

### pipeline/ — Code Bundles & Pipeline Builder
- **DCM project** with 3 code bundles (`ml + compute_pool`) and a 4-task DAG
- Weekly cron schedule → feature engineering → model training → deployment (quality gate + promote)
- Each code bundle is a self-contained Python script running on `SNOWHEALTH_COMPUTE_POOL`
- Deploy: `snow dcm deploy --from pipeline --target DEV`

## Synthetic Data

10,000 transactions with realistic retail pharmacy patterns:
- **8 stores** across 4 regions (Northeast, Southeast, Midwest, West)
- **15 SKUs** across 7 categories (Prescription, OTC Pain/Cold/Allergy/Digestive, Pharmacy Services, Health & Wellness)
- **4 fulfillment channels**: In-Store, Online-Delivery, Drive-Thru, Curbside-Pickup
- Seasonal patterns, temperature/flu correlation, promotions
- Date range: January 2023 – December 2024

## Snowflake ML Features Demonstrated

| Feature | Where Used |
|---------|------------|
| **Feature Store** | Managed DT feature view, 10-min refresh, Postgres-backed online serving |
| **Experiment Tracking** | 3 runs: xgboost_baseline, lightgbm_baseline, xgboost_tuned_sf_tuner |
| **Model Registry** | 2 versions (BASELINE_V1, TUNED_V1), default version management |
| **ML Tuner** | Ray Tune on SPCS compute pool, RandomSearch, 10 trials |
| **Batch Inference** | `mv.run()` (warehouse) and `mv.run_batch()` (SPCS, 1M rows) |
| **SPCS Inference Services** | Champion/challenger with `feature_sources_per_function` |
| **Gateway** | Traffic-split (90/10), stable endpoint for A/B comparison |
| **SHAP Explainability** | `explain` function, force plot, violin plot |
| **Model Monitor** | Version monitor with PSI, Diff of Means, Wasserstein drift metrics |
| **ML Lineage** | Source data → Feature View → Model tracking |
| **Pipeline Builder** | DCM project with code bundles, task DAG, weekly schedule |
| **Compute Pool** | `SNOWHEALTH_COMPUTE_POOL` for Tuner, batch jobs, inference services, and pipeline |

## Running the Solution

Execute notebooks in order (`01` → `07`). Each notebook imports shared code from `source/` and builds on the outputs of previous notebooks. The pipeline (`07`) requires a prior `snow dcm deploy` from the CLI.
