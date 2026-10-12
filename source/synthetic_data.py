"""
SnowHealth Demand Forecasting - Synthetic Data Generator
Generates realistic retail-pharmacy transaction data for the ML demo.
"""

from datetime import datetime

import numpy as np
import pandas as pd

# -- Reference data ------------------------------------------------------------

STORES = {
    "S001": {"region": "Northeast", "size": 8500, "staff": 25, "competitor_miles": 1.2},
    "S002": {"region": "Northeast", "size": 6200, "staff": 18, "competitor_miles": 3.5},
    "S003": {
        "region": "Southeast",
        "size": 10000,
        "staff": 30,
        "competitor_miles": 0.8,
    },
    "S004": {"region": "Southeast", "size": 7500, "staff": 22, "competitor_miles": 2.1},
    "S005": {"region": "Midwest", "size": 9000, "staff": 27, "competitor_miles": 4.0},
    "S006": {"region": "Midwest", "size": 5500, "staff": 15, "competitor_miles": 1.5},
    "S007": {"region": "West", "size": 11000, "staff": 32, "competitor_miles": 0.5},
    "S008": {"region": "West", "size": 7000, "staff": 20, "competitor_miles": 2.8},
}

SKUS = [
    ("SKU001", "Amoxicillin 500mg", "Prescription", 45.00),
    ("SKU002", "Lisinopril 10mg", "Prescription", 22.50),
    ("SKU003", "Metformin 500mg", "Prescription", 18.00),
    ("SKU004", "Ibuprofen 200mg", "OTC Pain Relief", 8.99),
    ("SKU005", "Acetaminophen 500mg", "OTC Pain Relief", 7.49),
    ("SKU006", "DayQuil Cold & Flu", "OTC Cold & Flu", 12.99),
    ("SKU007", "NyQuil Severe", "OTC Cold & Flu", 14.49),
    ("SKU008", "Claritin 24hr", "OTC Allergy", 19.99),
    ("SKU009", "Zyrtec 10mg", "OTC Allergy", 21.99),
    ("SKU010", "Pepto-Bismol", "OTC Digestive", 9.99),
    ("SKU011", "Flu Shot", "Pharmacy Services", 0.00),
    ("SKU012", "COVID Test Kit", "Pharmacy Services", 24.99),
    ("SKU013", "Multivitamin Daily", "Health & Wellness", 15.99),
    ("SKU014", "Sunscreen SPF50", "Beauty", 11.99),
    ("SKU015", "Hand Sanitizer 8oz", "Health & Wellness", 4.99),
]

CHANNELS = ["In-Store", "Online-Delivery", "Drive-Thru", "Curbside-Pickup"]
CHANNEL_WEIGHTS = [0.45, 0.25, 0.15, 0.15]

SEASON_MAP = {
    "Prescription": [1.0] * 12,
    "OTC Pain Relief": [1.1, 1.0, 0.9, 0.9, 0.8, 0.8, 0.8, 0.9, 1.0, 1.0, 1.1, 1.2],
    "OTC Cold & Flu": [1.5, 1.3, 1.0, 0.7, 0.5, 0.4, 0.4, 0.5, 0.7, 1.0, 1.3, 1.6],
    "OTC Allergy": [0.5, 0.7, 1.3, 1.6, 1.5, 1.2, 0.8, 0.7, 0.8, 0.9, 0.6, 0.5],
    "OTC Digestive": [0.9, 0.9, 1.0, 1.0, 1.1, 1.2, 1.2, 1.1, 1.0, 1.0, 1.1, 1.1],
    "Pharmacy Services": [1.4, 1.2, 0.9, 0.7, 0.6, 0.5, 0.5, 0.6, 1.0, 1.3, 1.5, 1.4],
    "Health & Wellness": [1.2, 1.1, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.1, 1.2],
    "Beauty": [0.7, 0.7, 0.9, 1.0, 1.3, 1.5, 1.5, 1.4, 1.1, 0.9, 0.7, 0.7],
}

REGION_TEMP_BASE = {"Northeast": 35, "Southeast": 55, "Midwest": 30, "West": 50}


def generate_transactions(n_rows: int = 10000, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic retail-pharmacy demand transactions.

    Args:
        n_rows: Number of transaction rows to generate.
        seed:   Random seed for reproducibility.

    Returns:
        DataFrame with 25 columns matching the SNOWHEALTH_DEMAND_TRANSACTIONS schema.
    """
    np.random.seed(seed)

    date_range = pd.date_range(datetime(2023, 1, 1), datetime(2024, 12, 31))
    store_ids = list(STORES.keys())
    sku_data = {s[0]: s for s in SKUS}
    sku_ids = [s[0] for s in SKUS]

    rows = []
    for i in range(n_rows):
        store_id = np.random.choice(store_ids)
        sku_id = np.random.choice(sku_ids)
        txn_date = pd.Timestamp(np.random.choice(date_range))
        channel = np.random.choice(CHANNELS, p=CHANNEL_WEIGHTS)

        store = STORES[store_id]
        sku = sku_data[sku_id]
        month = txn_date.month
        dow = txn_date.dayofweek

        # Seasonal demand multiplier
        cat_season = SEASON_MAP[sku[2]][month - 1]

        # Temperature: seasonal curve + region baseline + noise
        season_offset = 25 * np.sin(2 * np.pi * (month - 1) / 12 - np.pi / 3)
        temp_f = (
            REGION_TEMP_BASE[store["region"]] + season_offset + np.random.normal(0, 5)
        )
        temp_f = round(float(np.clip(temp_f, 5, 105)), 1)

        # Flu index: inversely correlated with temperature
        flu_base = max(0, (70 - temp_f) / 10)
        flu_index = round(float(np.clip(flu_base + np.random.normal(0, 0.8), 0, 10)), 1)

        # Promotion: ~20% of transactions
        promo_flag = np.random.random() < 0.20
        promo_pct = (
            round(float(np.random.uniform(0.05, 0.30)), 2) if promo_flag else 0.0
        )

        # Weekend / holiday
        is_weekend = dow >= 5
        is_holiday = (
            (month == 12 and txn_date.day in [24, 25, 31])
            or (month == 1 and txn_date.day == 1)
            or (month == 7 and txn_date.day == 4)
            or (month == 11 and 22 <= txn_date.day <= 28 and dow == 3)
        )

        # Base demand with modifiers
        base_demand = 20 + np.random.exponential(10)
        demand = base_demand * cat_season
        if is_weekend:
            demand *= 1.15
        if promo_flag:
            demand *= 1 + promo_pct
        if is_holiday:
            demand *= 0.6
        demand *= 1 + (store["size"] - 7500) / 50000
        units_sold = max(1, round(demand + np.random.normal(0, 3)))

        # Derived columns
        unit_price = round(sku[3] * (1 - promo_pct), 2)
        revenue = round(units_sold * unit_price, 2)

        # Inventory / supply chain
        inv_on_hand = max(0, int(units_sold * np.random.uniform(1.5, 5.0)))
        days_supply = round(inv_on_hand / max(units_sold, 1), 1)
        lead_time_days = int(np.random.choice([2, 3, 5, 7, 10]))

        rows.append(
            {
                "TRANSACTION_ID": f"TXN{i + 1:06d}",
                "TRANSACTION_DATE": txn_date.strftime("%Y-%m-%d"),
                "STORE_ID": store_id,
                "REGION": store["region"],
                "SKU_ID": sku_id,
                "PRODUCT_NAME": sku[1],
                "PRODUCT_CATEGORY": sku[2],
                "FULFILLMENT_CHANNEL": channel,
                "UNITS_SOLD": units_sold,
                "UNIT_PRICE": unit_price,
                "REVENUE": revenue,
                "PROMOTION_FLAG": promo_flag,
                "PROMOTION_DISCOUNT_PCT": promo_pct,
                "DAY_OF_WEEK": dow,
                "IS_WEEKEND": is_weekend,
                "IS_HOLIDAY": is_holiday,
                "TEMPERATURE_F": temp_f,
                "FLU_INDEX": flu_index,
                "STORE_SIZE_SQFT": store["size"],
                "STAFF_COUNT": store["staff"],
                "COMPETITOR_PROXIMITY_MILES": store["competitor_miles"],
                "INVENTORY_ON_HAND": inv_on_hand,
                "DAYS_SUPPLY_ON_HAND": days_supply,
                "LEAD_TIME_DAYS": lead_time_days,
                "CREATED_AT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return pd.DataFrame(rows)
