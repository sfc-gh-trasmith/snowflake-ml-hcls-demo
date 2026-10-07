# SnowHealth Demand Forecasting - ML Solution

## Overview

End-to-end machine learning time-series forecasting solution for a retail pharmacy company (SnowHealth) to predict demand for prescription medications, over-the-counter products, and pharmacy services. The solution covers data ingestion, feature engineering, model training, hyperparameter tuning, deployment, and monitoring across SKUs, stores, regions, fulfillment channels, and time periods.

## Business Use Cases

| Use Case | How This Solution Helps |
|----------|------------------------|
| **Inventory Replenishment** | Predict units sold per SKU-store to optimize reorder points and safety stock |
| **Medication Purchasing** | Forecast prescription drug demand to negotiate volume contracts with suppliers |
| **Store & Fulfillment Planning** | Model demand by channel (in-store, online, drive-thru, curbside) for staffing |
| **Distribution** | Regional demand forecasts to optimize DC-to-store allocation |
| **Workforce Scheduling** | Predict service demand (flu shots, COVID tests) for pharmacy staff scheduling |
| **Capacity Management** | Store-level demand trends to inform expansion or right-sizing decisions |
| **Customer Service** | Reduce stockouts and improve fill rates through accurate demand prediction |

## Architecture

```
SNOWHEALTH_ML_DB (Database)
├── SNOWHEALTH_RAW (Schema)          - Raw transaction data
│   └── SNOWHEALTH_DEMAND_TRANSACTIONS (10,000 rows)
├── SNOWHEALTH_FEATURES (Schema)     - Feature Store
│   ├── SNOWHEALTH_DEMAND_FEATURES   - Engineered feature table
│   ├── SNOWHEALTH_SKU_STORE         - Entity (join keys: SKU_ID, STORE_ID)
│   └── SNOWHEALTH_DEMAND_FV (V01)   - Managed FV (DT, 10-min refresh, online serving)
└── SNOWHEALTH_MODELS (Schema)       - Model Registry & Monitoring
    ├── SNOWHEALTH_DEMAND_FORECAST   - Registered model (baseline_v1, tuned_v1)
    ├── SNOWHEALTH_DEMAND_PREDICTIONS - Prediction output table
    ├── SNOWHEALTH_DEMAND_MONITOR_SOURCE - Monitoring source table
    └── SNOWHEALTH_DEMAND_DRIFT_ALERT - Drift detection alert
```

## Project Structure

```
├── source/                          # Python modules (imported by notebooks)
│   ├── config.py                    # Configuration: DB names, model params, feature lists
│   ├── feature_engineering.py       # Feature transforms: calendar, cyclical, lag, interaction
│   └── model_utils.py              # Training, evaluation, comparison, artifact helpers
│
├── 01_setup.ipynb                   # Notebook 1: Infrastructure & data exploration
├── 02_feature_engineering.ipynb     # Notebook 2: Feature engineering & online feature store
├── 03_model_training.ipynb          # Notebook 3: Model training (XGBoost + LightGBM)
├── 04_hyperparameter_tuning.ipynb   # Notebook 4: HPO comparison (baseline vs tuned)
├── 05_deployment_monitoring.ipynb   # Notebook 5: Deployment & drift monitoring
├── 06_drift_simulation.ipynb        # Notebook 6: 1M inference load test with drift
└── README.md                        # This documentation
```

## Notebooks Walkthrough

### 1. 01_setup.ipynb - Infrastructure Setup
- Validates database objects (SNOWHEALTH_ML_DB, schemas)
- Explores the synthetic dataset (10,000 transactions)
- Visualizes data distributions across regions, categories, channels
- Shows daily demand trend with rolling averages

### 2. 02_feature_engineering.ipynb - Feature Engineering & Online Feature Store
- **Calendar features**: Month, quarter, week of year, weekend/holiday flags
- **Cyclical encoding**: sin/cos transforms for month and day-of-week
- **Lag features**: 7-day, 14-day, 30-day lag values per SKU-store
- **Rolling averages**: 7-day and 30-day rolling mean demand
- **Interaction features**: price x promotion, inventory turnover ratio, seasonal index
- Registers entity (SNOWHEALTH_SKU_STORE) and **managed Feature View** (Dynamic Table, 10-min refresh)
- Enables **online feature serving** with 1-minute target lag for low-latency key-value lookups
- Verifies online store with a sample lookup

### 3. 03_model_training.ipynb - Model Training with Experiment Tracking
- **Two models trained**: XGBoost Regressor and LightGBM Regressor
- **Snowflake Experiment Tracking**: Logs parameters, metrics, and feature importance artifacts
- **Feature importance artifacts**: Saved as JSON files per model run
- Side-by-side model comparison (MAE, RMSE, MAPE, R2)
- Best model (LightGBM) registered to Snowflake Model Registry with `target_platforms=["WAREHOUSE"]`

### 4. 04_hyperparameter_tuning.ipynb - HPO Comparison
- **Baseline**: Default XGBoost parameters
- **Tuned**: RandomizedSearchCV over 20 configurations, 3-fold CV
- **Search space**: n_estimators, max_depth, learning_rate, subsample, colsample_bytree, min_child_weight, reg_alpha, reg_lambda
- Comparison report with improvement metrics
- Tuned model registered as `tuned_v1` and set as default version
- Includes reference code for Snowflake ML Tuner API (Container Runtime)

### 5. 05_deployment_monitoring.ipynb - Deployment & Monitoring
- **Batch inference**: Warehouse-based predictions via Model Registry `mv.run()`
- **Prediction table**: Results saved with residuals and error metrics
- **Model Monitor**: SQL-based drift detection setup
- **Drift alert**: Scheduled daily at 8 AM ET, triggers if RMSE > 6.0
- **Performance monitoring queries**: SQL for ongoing model health checks
- Deployment validation visualizations (actual vs predicted, residuals, error by store)

## Synthetic Data

10,000 transaction records with realistic retail pharmacy patterns:
- **8 stores** across 4 regions (Northeast, Southeast, Midwest, West)
- **15 SKUs** across 8 categories (Prescription, OTC Pain/Cold/Allergy/Digestive, Pharmacy Services, Health & Wellness, Beauty)
- **4 fulfillment channels**: In-Store, Online-Delivery, Drive-Thru, Curbside-Pickup
- **Seasonal patterns**: Cold/flu products peak in winter, allergy in spring, sunscreen in summer
- **Environmental features**: Temperature, flu index correlated with region and season
- **Date range**: January 2023 - December 2024

## Model Performance

| Model | MAE | RMSE | MAPE | R2 |
|-------|-----|------|------|-----|
| XGBoost Baseline | 3.44 | 4.55 | 11.30% | 0.931 |
| LightGBM Baseline | 3.41 | 4.45 | 11.26% | 0.934 |
| **XGBoost Tuned (HPO)** | **3.38** | **4.43** | **11.14%** | **0.935** |

Hyperparameter tuning improved RMSE by ~2.6% over the XGBoost baseline.

## Snowflake ML Features Used

| Feature | Usage |
|---------|-------|
| **Feature Store** | Managed DT feature view, 10-min refresh, online serving enabled |
| **Experiment Tracking** | 3 runs: xgboost_baseline, lightgbm_baseline, xgboost_tuned_hpo |
| **Model Registry** | 2 versions (baseline_v1, tuned_v1) with warehouse inference |
| **Model Monitor** | Drift detection on prediction source table |
| **Alerts** | Scheduled RMSE threshold monitoring with email notification |
| **Batch Inference** | Warehouse-based `mv.run()` for scoring |

## Key Configuration (source/config.py)

All database names, schema names, model names, feature lists, and hyperparameter spaces are centralized in `config.py` for easy modification and reuse across notebooks.

## Running the Solution

Execute the notebooks in order (01 through 06). Each notebook imports shared code from `source/` and builds on the outputs of previous notebooks. The database objects are created by SQL commands in the infrastructure setup phase.
