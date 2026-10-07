"""
SnowHealth Demand Forecasting - Feature Engineering Module
Transforms raw transaction data into ML-ready features.
"""
import pandas as pd
import numpy as np


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract calendar features from TRANSACTION_DATE."""
    df = df.copy()
    df["TRANSACTION_DATE"] = pd.to_datetime(df["TRANSACTION_DATE"])
    df["MONTH"] = df["TRANSACTION_DATE"].dt.month
    df["QUARTER"] = df["TRANSACTION_DATE"].dt.quarter
    df["WEEK_OF_YEAR"] = df["TRANSACTION_DATE"].dt.isocalendar().week.astype(int)
    df["IS_WEEKEND_INT"] = df["IS_WEEKEND"].astype(int)
    df["IS_HOLIDAY_INT"] = df["IS_HOLIDAY"].astype(int)
    df["IS_PROMOTION_INT"] = df["PROMOTION_FLAG"].astype(int)
    return df


def add_cyclical_features(df: pd.DataFrame) -> pd.DataFrame:
    """Encode cyclical time features using sin/cos transforms."""
    df = df.copy()
    df["MONTH_SIN"] = np.sin(2 * np.pi * df["MONTH"] / 12)
    df["MONTH_COS"] = np.cos(2 * np.pi * df["MONTH"] / 12)
    df["DOW_SIN"] = np.sin(2 * np.pi * df["DAY_OF_WEEK"] / 7)
    df["DOW_COS"] = np.cos(2 * np.pi * df["DAY_OF_WEEK"] / 7)
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute lag and rolling window features per SKU-Store pair."""
    df = df.copy()
    df = df.sort_values(["SKU_ID", "STORE_ID", "TRANSACTION_DATE"])
    group_cols = ["SKU_ID", "STORE_ID"]

    df["ROLLING_7D_AVG_UNITS"] = (
        df.groupby(group_cols)["UNITS_SOLD"]
        .transform(lambda x: x.rolling(window=7, min_periods=1).mean())
    )
    df["ROLLING_30D_AVG_UNITS"] = (
        df.groupby(group_cols)["UNITS_SOLD"]
        .transform(lambda x: x.rolling(window=30, min_periods=1).mean())
    )
    df["LAG_7D_UNITS"] = df.groupby(group_cols)["UNITS_SOLD"].shift(7)
    df["LAG_14D_UNITS"] = df.groupby(group_cols)["UNITS_SOLD"].shift(14)
    df["LAG_30D_UNITS"] = df.groupby(group_cols)["UNITS_SOLD"].shift(30)

    lag_cols = ["LAG_7D_UNITS", "LAG_14D_UNITS", "LAG_30D_UNITS"]
    for col in lag_cols:
        df[col] = df[col].fillna(df["UNITS_SOLD"].median())
    return df


def add_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create business-meaningful feature interactions."""
    df = df.copy()
    df["PRICE_TIMES_PROMO"] = df["UNIT_PRICE"] * df["PROMOTION_DISCOUNT_PCT"]
    df["INVENTORY_TURNOVER_RATIO"] = np.where(
        df["INVENTORY_ON_HAND"] > 0,
        df["UNITS_SOLD"] / df["INVENTORY_ON_HAND"],
        0
    )
    seasonal_map = {1: 0.8, 2: 0.9, 3: 1.0, 4: 1.1, 5: 1.2, 6: 1.1,
                    7: 1.0, 8: 0.9, 9: 1.1, 10: 1.2, 11: 1.3, 12: 1.1}
    df["SEASONAL_DEMAND_INDEX"] = df["MONTH"].map(seasonal_map)
    return df


def encode_categoricals(df: pd.DataFrame, categorical_cols: list) -> pd.DataFrame:
    """One-hot encode categorical features, returning numeric DataFrame."""
    df = df.copy()
    df = pd.get_dummies(df, columns=categorical_cols, drop_first=True, dtype=int)
    return df


def engineer_features(df: pd.DataFrame, categorical_cols: list) -> pd.DataFrame:
    """Full feature engineering pipeline."""
    df = add_calendar_features(df)
    df = add_cyclical_features(df)
    df = add_lag_features(df)
    df = add_interaction_features(df)
    df = encode_categoricals(df, categorical_cols)
    return df


def get_feature_columns(df: pd.DataFrame, target: str, exclude_cols: list = None) -> list:
    """Return the list of feature column names (all numeric, excluding target and IDs)."""
    if exclude_cols is None:
        exclude_cols = [
            "TRANSACTION_ID", "TRANSACTION_DATE", "STORE_ID", "SKU_ID",
            "PRODUCT_NAME", "CREATED_AT", "REVENUE", "IS_WEEKEND",
            "IS_HOLIDAY", "PROMOTION_FLAG"
        ]
    exclude_cols.append(target)
    return [c for c in df.columns if c not in exclude_cols and df[c].dtype in ["int64", "float64", "int32", "float32", "uint8"]]
