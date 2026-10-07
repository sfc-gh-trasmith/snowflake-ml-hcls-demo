"""
SnowHealth Demand Forecasting - Configuration Module
Central configuration for database objects, model parameters, and feature definitions.
"""

# -- Snowflake Database Objects --
SNOWHEALTH_DATABASE = "SNOWHEALTH_ML_DB"
SNOWHEALTH_RAW_SCHEMA = "SNOWHEALTH_RAW"
SNOWHEALTH_FEATURES_SCHEMA = "SNOWHEALTH_FEATURES"
SNOWHEALTH_MODELS_SCHEMA = "SNOWHEALTH_MODELS"

# -- Table Names --
SNOWHEALTH_TRANSACTIONS_TABLE = f"{SNOWHEALTH_DATABASE}.{SNOWHEALTH_RAW_SCHEMA}.SNOWHEALTH_DEMAND_TRANSACTIONS"
SNOWHEALTH_FEATURE_TABLE = f"{SNOWHEALTH_DATABASE}.{SNOWHEALTH_FEATURES_SCHEMA}.SNOWHEALTH_DEMAND_FEATURES"
SNOWHEALTH_PREDICTIONS_TABLE = f"{SNOWHEALTH_DATABASE}.{SNOWHEALTH_MODELS_SCHEMA}.SNOWHEALTH_DEMAND_PREDICTIONS"
SNOWHEALTH_MONITORING_TABLE = f"{SNOWHEALTH_DATABASE}.{SNOWHEALTH_MODELS_SCHEMA}.SNOWHEALTH_DEMAND_MONITOR_SOURCE"

# -- Model Registry Names --
SNOWHEALTH_MODEL_NAME = "SNOWHEALTH_DEMAND_FORECAST"
SNOWHEALTH_EXPERIMENT_NAME = "SNOWHEALTH_DEMAND_FORECAST_EXPERIMENT"

# -- Feature Store --
SNOWHEALTH_FEATURE_STORE_SCHEMA = SNOWHEALTH_FEATURES_SCHEMA
SNOWHEALTH_ENTITY_NAME = "SNOWHEALTH_SKU_STORE"
SNOWHEALTH_FEATURE_VIEW_NAME = "SNOWHEALTH_DEMAND_FV"
SNOWHEALTH_FEATURE_VIEW_VERSION = "V01"

# -- Feature Columns --
CATEGORICAL_FEATURES = [
    "REGION", "PRODUCT_CATEGORY", "FULFILLMENT_CHANNEL"
]

NUMERIC_FEATURES = [
    "UNIT_PRICE", "PROMOTION_DISCOUNT_PCT", "DAY_OF_WEEK",
    "TEMPERATURE_F", "FLU_INDEX", "STORE_SIZE_SQFT", "STAFF_COUNT",
    "COMPETITOR_PROXIMITY_MILES", "INVENTORY_ON_HAND",
    "DAYS_SUPPLY_ON_HAND", "LEAD_TIME_DAYS",
    "MONTH", "QUARTER", "WEEK_OF_YEAR",
    "IS_WEEKEND_INT", "IS_HOLIDAY_INT", "IS_PROMOTION_INT",
    "MONTH_SIN", "MONTH_COS", "DOW_SIN", "DOW_COS",
    "ROLLING_7D_AVG_UNITS", "ROLLING_30D_AVG_UNITS",
    "LAG_7D_UNITS", "LAG_14D_UNITS", "LAG_30D_UNITS",
    "PRICE_TIMES_PROMO", "INVENTORY_TURNOVER_RATIO",
    "SEASONAL_DEMAND_INDEX"
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
