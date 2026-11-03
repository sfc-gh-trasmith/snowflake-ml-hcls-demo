-- ============================================================================
-- Per-environment bootstrap — run by CI (as the target's deployer role) before
-- `snow feature apply` and `snow dcm deploy`. Idempotent.
--
--   snow sql -f scripts/bootstrap_env.sql -D "db=DEV_MLOPS_DB" -x
--
-- Creates the objects neither DCM nor the feature store project manage:
--   * the DCM project object itself
--   * the code-bundle results stage and the deploy log (written by tasks)
--   * the feature table schema, so the feature view's batch source resolves
--     before the first pipeline run populates it
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS <% db %>.MODELS;

CREATE DCM PROJECT IF NOT EXISTS <% db %>.MODELS.MLOPS_PIPELINE;

CREATE STAGE IF NOT EXISTS <% db %>.MODELS.MLOPS_PIPELINE_RESULTS
    COMMENT = 'Code bundle results for MLOPS_PIPELINE';

CREATE TABLE IF NOT EXISTS <% db %>.MODELS.MLOPS_PIPELINE_DEPLOY_LOG (
    MODEL_NAME VARCHAR,
    VERSION VARCHAR,
    DEPLOYED_AT TIMESTAMP_NTZ,
    RMSE FLOAT,
    STATUS VARCHAR
);

-- Output of MLOPS_TASK_FEATURE_ENGINEERING (written with mode("truncate"))
CREATE TABLE IF NOT EXISTS <% db %>.MODELS.MLOPS_PIPELINE_FEATURES (
    TRANSACTION_ID VARCHAR,
    TRANSACTION_DATE TIMESTAMP_NTZ,
    STORE_ID VARCHAR,
    SKU_ID VARCHAR,
    PRODUCT_NAME VARCHAR,
    REGION VARCHAR,
    PRODUCT_CATEGORY VARCHAR,
    FULFILLMENT_CHANNEL VARCHAR,
    UNITS_SOLD NUMBER(38,0),
    UNIT_PRICE FLOAT,
    PROMOTION_DISCOUNT_PCT FLOAT,
    DAY_OF_WEEK NUMBER(38,0),
    IS_WEEKEND_INT NUMBER(38,0),
    IS_HOLIDAY_INT NUMBER(38,0),
    IS_PROMOTION_INT NUMBER(38,0),
    TEMPERATURE_F FLOAT,
    FLU_INDEX FLOAT,
    STORE_SIZE_SQFT NUMBER(38,0),
    STAFF_COUNT NUMBER(38,0),
    COMPETITOR_PROXIMITY_MILES FLOAT,
    INVENTORY_ON_HAND NUMBER(38,0),
    DAYS_SUPPLY_ON_HAND FLOAT,
    LEAD_TIME_DAYS NUMBER(38,0),
    MONTH NUMBER(38,0),
    QUARTER NUMBER(38,0),
    WEEK_OF_YEAR NUMBER(38,0),
    MONTH_SIN FLOAT,
    MONTH_COS FLOAT,
    DOW_SIN FLOAT,
    DOW_COS FLOAT,
    ROLLING_7D_AVG FLOAT,
    ROLLING_30D_AVG FLOAT,
    LAG_7D FLOAT,
    LAG_14D FLOAT,
    PRICE_X_PROMO FLOAT,
    INVENTORY_TURNOVER FLOAT,
    SEASONAL_INDEX FLOAT
);
