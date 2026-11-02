"""
MLOps with DCM - Configuration Module
Central configuration for database objects, model parameters, and feature definitions.
"""

# -- Snowflake Database Objects --
MLOPS_DATABASE = "DEV_MLOPS_DB"
MLOPS_RAW_SCHEMA = "RAW"
MLOPS_FEATURES_SCHEMA = "FEATURES"
MLOPS_MODELS_SCHEMA = "MODELS"

# -- Table Names --
MLOPS_TRANSACTIONS_TABLE = (
    f"{MLOPS_DATABASE}.{MLOPS_RAW_SCHEMA}.MLOPS_DEMAND_TRANSACTIONS"
)
MLOPS_FEATURE_TABLE = (
    f"{MLOPS_DATABASE}.{MLOPS_FEATURES_SCHEMA}.MLOPS_DEMAND_FEATURES"
)
MLOPS_PREDICTIONS_TABLE = (
    f"{MLOPS_DATABASE}.{MLOPS_MODELS_SCHEMA}.MLOPS_DEMAND_PREDICTIONS"
)
MLOPS_MONITORING_TABLE = (
    f"{MLOPS_DATABASE}.{MLOPS_MODELS_SCHEMA}.MLOPS_DEMAND_MONITOR_SOURCE"
)

# -- Model Registry Names --
MLOPS_MODEL_NAME = "MLOPS_DEMAND_FORECAST"
MLOPS_EXPERIMENT_NAME = "MLOPS_DEMAND_FORECAST_EXPERIMENT"

# -- Compute Pool (for ML Jobs, HPO Tuner, and Model Serving) --
MLOPS_COMPUTE_POOL = "MLOPS_COMPUTE_POOL"

# -- Feature Store --
MLOPS_FEATURE_STORE_SCHEMA = MLOPS_FEATURES_SCHEMA
MLOPS_ENTITY_NAME = "MLOPS_SKU_STORE"
MLOPS_FEATURE_VIEW_NAME = "MLOPS_DEMAND_FV"
MLOPS_FEATURE_VIEW_VERSION = "V01"

# -- Feature Columns --
CATEGORICAL_FEATURES = ["REGION", "PRODUCT_CATEGORY", "FULFILLMENT_CHANNEL"]

NUMERIC_FEATURES = [
    "UNIT_PRICE",
    "PROMOTION_DISCOUNT_PCT",
    "DAY_OF_WEEK",
    "TEMPERATURE_F",
    "FLU_INDEX",
    "STORE_SIZE_SQFT",
    "STAFF_COUNT",
    "COMPETITOR_PROXIMITY_MILES",
    "INVENTORY_ON_HAND",
    "DAYS_SUPPLY_ON_HAND",
    "LEAD_TIME_DAYS",
    "MONTH",
    "QUARTER",
    "WEEK_OF_YEAR",
    "IS_WEEKEND_INT",
    "IS_HOLIDAY_INT",
    "IS_PROMOTION_INT",
    "MONTH_SIN",
    "MONTH_COS",
    "DOW_SIN",
    "DOW_COS",
    "ROLLING_7D_AVG_UNITS",
    "ROLLING_30D_AVG_UNITS",
    "LAG_7D_UNITS",
    "LAG_14D_UNITS",
    "LAG_30D_UNITS",
    "PRICE_TIMES_PROMO",
    "INVENTORY_TURNOVER_RATIO",
    "SEASONAL_DEMAND_INDEX",
]

TARGET_COLUMN = "UNITS_SOLD"

ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# -- Model Training --
TEST_SIZE = 0.2
RANDOM_STATE = 42

# -- XGBoost Baseline Parameters --
XGBOOST_BASELINE_PARAMS = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": RANDOM_STATE,
    "objective": "reg:squarederror",
    "tree_method": "hist",
}

# -- LightGBM Baseline Parameters --
LIGHTGBM_BASELINE_PARAMS = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": RANDOM_STATE,
    "objective": "regression",
    "verbose": -1,
}

# -- Hyperparameter Tuning Search Space --
HPO_SEARCH_SPACE = {
    "n_estimators": [100, 200, 300, 500],
    "max_depth": [4, 6, 8, 10],
    "learning_rate": [0.01, 0.05, 0.1, 0.2],
    "subsample": [0.7, 0.8, 0.9, 1.0],
    "colsample_bytree": [0.7, 0.8, 0.9, 1.0],
    "min_child_weight": [1, 3, 5, 7],
    "reg_alpha": [0, 0.01, 0.1, 1.0],
    "reg_lambda": [0.5, 1.0, 2.0, 5.0],
}
