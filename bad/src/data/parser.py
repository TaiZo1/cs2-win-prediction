"""
CS2 Demo Parser - Feature Extraction Module
Author: Lucas Lachaume
Date: December 2024

This module extracts round-level economic and tactical features from CS2 professional demos.
Features are extracted at freeze-time (t=15s) to capture initial round state before gameplay begins.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from demoparser2 import DemoParser
from awpy import Demo


# ============================================
# WEAPON & ITEM DEFINITIONS
# ============================================

PISTOLS = {
    "Glock-18",
    "USP-S",
    "Tec-9",
    "P2000",
    "P250",
    "Dual Berettas",
    "CZ75-Auto",
    "Five-SeveN",
    "R8 Revolver",
    "Desert Eagle",
}

SMGS = {"MAC-10", "MP9", "UMP-45", "PP-Bizon", "MP5-SD", "MP7", "P90"}

HEAVY = {"Nova", "Sawed-Off", "MAG-7", "XM1014", "M249", "Negev"}

RIFLES = {
    "Galil AR",
    "FAMAS",
    "AK-47",
    "M4A1-S",
    "M4A4",
    "AUG",
    "SG 553",
    "G3SG1",
    "SCAR-20",
}

SNIPERS = {"SSG 08", "AWP"}

GRENADES = {
    "High Explosive Grenade",
    "Flashbang",
    "Smoke Grenade",
    "Molotov",
    "Incendiary Grenade",
    "Decoy Grenade",
}

ITEM_PRICES = {
    # Equipment
    "Kevlar Vest": 650,
    "Kevlar & Helmet": 1000,
    "Zeus x27": 200,
    "Defuse Kit": 400,
    # Bomb
    "C4 Explosive": 0,
    # Starting Pistols
    "Glock-18": 200,
    "USP-S": 200,
    "P2000": 200,
    # Pistols
    "Dual Berettas": 300,
    "P250": 300,
    "Tec-9": 500,
    "Five-SeveN": 500,
    "CZ75-Auto": 500,
    "Desert Eagle": 700,
    "R8 Revolver": 600,
    # SMG
    "MAC-10": 1050,
    "MP9": 1250,
    "MP7": 1500,
    "MP5-SD": 1500,
    "UMP-45": 1200,
    "P90": 2350,
    "PP-Bizon": 1400,
    # Heavy
    "Nova": 1050,
    "Sawed-Off": 1100,
    "MAG-7": 1300,
    "XM1014": 2000,
    "M249": 5200,
    "Negev": 1700,
    # Rifles
    "Galil AR": 1800,
    "FAMAS": 1950,
    "AK-47": 2700,
    "M4A4": 2900,
    "M4A1-S": 2900,
    "SG 553": 3000,
    "AUG": 3300,
    "SSG 08": 1700,
    "AWP": 4750,
    "G3SG1": 5000,
    "SCAR-20": 5000,
    # Grenades
    "Molotov": 400,
    "Incendiary Grenade": 500,
    "Decoy Grenade": 50,
    "Flashbang": 200,
    "High Explosive Grenade": 300,
    "Smoke Grenade": 300,
    # Knives (cosmetic, value 0)
    "Stock Knife": 0,
    "Bayonet": 0,
    "Butterfly Knife": 0,
    "Falchion Knife": 0,
    "Flip Knife": 0,
    "Gut Knife": 0,
    "Huntsman Knife": 0,
    "Karambit": 0,
    "M9 Bayonet": 0,
    "Shadow Daggers": 0,
    "Bowie Knife": 0,
    "Ursus Knife": 0,
    "Navaja Knife": 0,
    "Stiletto Knife": 0,
    "Talon Knife": 0,
    "Classic Knife": 0,
    "Skeleton Knife": 0,
    "Paracord Knife": 0,
    "Survival Knife": 0,
    "Nomad Knife": 0,
    "Kukri Knife": 0,
}

ALL_WEAPON_DICT = {
    **{w: ITEM_PRICES[w] for w in RIFLES},
    **{w: ITEM_PRICES[w] for w in SMGS},
    **{w: ITEM_PRICES[w] for w in PISTOLS},
    **{w: ITEM_PRICES[w] for w in SNIPERS},
    **{w: ITEM_PRICES[w] for w in HEAVY},
}


# ============================================
# HELPER FUNCTIONS
# ============================================


def count_weapon(snapshot_data, weapon):
    """Count number of specific weapons in team inventory"""
    if isinstance(weapon, str):
        weapons = [weapon]
    else:
        weapons = list(weapon)

    inv = snapshot_data["inventory"]
    inv_series = inv.explode()

    return inv_series.isin(weapons).sum()


def count_all_weapon(snapshot_data):
    """Calculate total weapon value for a team"""
    total_value = 0

    for weapon, price in ALL_WEAPON_DICT.items():
        count = count_weapon(snapshot_data, weapon)
        total_value += count * price

    return total_value


def count_items(snapshot_data, grenade_df, item):
    """
    Count items (primarily grenades) accounting for both inventory and thrown grenades.

    Args:
        snapshot_data: DataFrame with player inventory at snapshot tick
        grenade_df: DataFrame with grenades thrown between freeze_end and snapshot
        item: Item name (str) or set of item names

    Returns:
        Total count of items (inventory + thrown)
    """
    if isinstance(item, str):
        items = {item}
    else:
        items = set(item)

    # Count in inventory
    inv_count = snapshot_data["inventory"].explode().isin(items).sum()

    # Count thrown grenades
    throw_count = 0
    if grenade_df is not None and not grenade_df.empty:
        throw_count = grenade_df["grenade_type"].isin(items).sum()

    return int(inv_count + throw_count)


def build_grenade_df(demawpy, start_tick, end_tick):
    """
    Extract grenades thrown between start_tick and end_tick.

    Args:
        demawpy: Awpy Demo object
        start_tick: Start tick (freeze_end + 1)
        end_tick: End tick (snapshot_tick)

    Returns:
        DataFrame with columns: [tick, thrower, grenade_type]
    """
    g = demawpy.grenades.to_pandas().copy()

    # Filter by tick range
    g = g[(g["tick"] > start_tick) & (g["tick"] <= end_tick)].copy()
    if g.empty:
        return pd.DataFrame(columns=["tick", "thrower", "grenade_type"])

    # Filter grenades with valid positions
    pos_mask = g[["X", "Y", "Z"]].notna().all(axis=1)
    g = g[pos_mask].copy()
    if g.empty:
        return pd.DataFrame(columns=["tick", "thrower", "grenade_type"])

    # Keep first occurrence of each grenade entity
    g = g.sort_values("tick").drop_duplicates(subset=["entity_id"], keep="first").copy()

    # Clean grenade type names
    raw = g["grenade_type"].astype(str)
    raw = raw.str.replace(r"^C", "", regex=True)
    raw = raw.str.replace(r"Projectile$", "", regex=True)

    mapping = {
        "SmokeGrenade": "Smoke Grenade",
        "Flashbang": "Flashbang",
        "HEGrenade": "High Explosive Grenade",
        "MolotovGrenade": "Molotov",
        "IncendiaryGrenade": "Incendiary Grenade",
        "DecoyGrenade": "Decoy Grenade",
    }
    g["grenade_type"] = raw.map(mapping).fillna(raw)

    return (
        g[["tick", "thrower", "grenade_type"]]
        .sort_values("tick")
        .reset_index(drop=True)
    )


# ============================================
# MAIN EXTRACTION FUNCTION
# ============================================


def extract_round_features(
    start_tick_data,
    round_number,
    snapshot_data,
    grenade_df,
    map_name,
    ct_score,
    t_score,
    round_winner,
    previous_round_data=None,
    previous_last_tick_data=None,
):
    """
    Extract all features for a single round at freeze-time.

    Args:
        start_tick_data: Player data at round start
        round_number: Current round number (1-30+)
        snapshot_data: Player data at snapshot tick (freeze_time + 2s)
        grenade_df: Grenades thrown between freeze_end and snapshot
        map_name: Map name (e.g., 'de_inferno')
        ct_score: CT team score
        t_score: T team score
        round_winner: 1 if CT won, 0 if T won
        previous_round_data: Features from previous round (for streaks)
        previous_last_tick_data: Player data at end of previous round (for equipment saved)

    Returns:
        dict: Dictionary with all extracted features
    """

    features = {}

    # Split data by team
    ct_start_data = start_tick_data[start_tick_data["team_side"] == "CT"]
    t_start_data = start_tick_data[start_tick_data["team_side"] == "T"]

    ct_snapshot_data = snapshot_data[snapshot_data["team_side"] == "CT"]
    t_snapshot_data = snapshot_data[snapshot_data["team_side"] == "T"]

    # Get player names for grenade filtering
    ct_names = set(ct_snapshot_data["name"])
    t_names = set(t_snapshot_data["name"])

    ct_grenade_df = (
        grenade_df[grenade_df["thrower"].isin(ct_names)]
        if grenade_df is not None
        else None
    )
    t_grenade_df = (
        grenade_df[grenade_df["thrower"].isin(t_names)]
        if grenade_df is not None
        else None
    )

    # ============================================
    # ECONOMY
    # ============================================

    features["ct_money_total"] = (
        ct_start_data["balance"].sum() + ct_start_data["current_equip_value"].sum()
    )
    features["t_money_total"] = (
        t_start_data["balance"].sum() + t_start_data["current_equip_value"].sum()
    )

    features["ct_cash"] = ct_snapshot_data["balance"].sum()
    features["t_cash"] = t_snapshot_data["balance"].sum()

    features["ct_cash_avg"] = features["ct_cash"] / 5
    features["t_cash_avg"] = features["t_cash"] / 5

    features["ct_armor_count"] = (ct_snapshot_data["armor_value"] > 0).sum()
    features["t_armor_count"] = (t_snapshot_data["armor_value"] > 0).sum()

    features["ct_helmet_count"] = (ct_snapshot_data["has_helmet"]).sum()
    features["t_helmet_count"] = (t_snapshot_data["has_helmet"]).sum()

    features["ct_defuser_count"] = (ct_snapshot_data["has_defuser"]).sum()

    # ============================================
    # ARMAMENT
    # ============================================

    features["ct_awp_count"] = count_weapon(ct_snapshot_data, "AWP")
    features["t_awp_count"] = count_weapon(t_snapshot_data, "AWP")

    features["ct_ssg_count"] = count_weapon(ct_snapshot_data, "SSG 08")
    features["t_ssg_count"] = count_weapon(t_snapshot_data, "SSG 08")

    features["ct_rifle_count"] = count_weapon(ct_snapshot_data, RIFLES)
    features["t_rifle_count"] = count_weapon(t_snapshot_data, RIFLES)

    features["ct_smg_count"] = count_weapon(ct_snapshot_data, SMGS)
    features["t_smg_count"] = count_weapon(t_snapshot_data, SMGS)

    features["ct_heavy_count"] = count_weapon(ct_snapshot_data, HEAVY)
    features["t_heavy_count"] = count_weapon(t_snapshot_data, HEAVY)

    features["ct_ak_count"] = count_weapon(ct_snapshot_data, "AK-47")

    # ============================================
    # UTILITY
    # ============================================

    features["ct_smoke_count"] = count_items(
        ct_snapshot_data, ct_grenade_df, "Smoke Grenade"
    )
    features["t_smoke_count"] = count_items(
        t_snapshot_data, t_grenade_df, "Smoke Grenade"
    )

    features["ct_molo_count"] = count_items(
        ct_snapshot_data, ct_grenade_df, ["Incendiary Grenade", "Molotov"]
    )
    features["t_molo_count"] = count_items(
        t_snapshot_data, t_grenade_df, ["Incendiary Grenade", "Molotov"]
    )

    features["ct_flash_count"] = count_items(
        ct_snapshot_data, ct_grenade_df, "Flashbang"
    )
    features["t_flash_count"] = count_items(t_snapshot_data, t_grenade_df, "Flashbang")

    features["ct_he_count"] = count_items(
        ct_snapshot_data, ct_grenade_df, "High Explosive Grenade"
    )
    features["t_he_count"] = count_items(
        t_snapshot_data, t_grenade_df, "High Explosive Grenade"
    )

    features["ct_utility_value"] = (
        features["ct_smoke_count"] * ITEM_PRICES["Smoke Grenade"]
        + features["ct_flash_count"] * ITEM_PRICES["Flashbang"]
        + features["ct_he_count"] * ITEM_PRICES["High Explosive Grenade"]
        + count_items(ct_snapshot_data, ct_grenade_df, "Molotov")
        * ITEM_PRICES["Molotov"]
        + count_items(ct_snapshot_data, ct_grenade_df, "Incendiary Grenade")
        * ITEM_PRICES["Incendiary Grenade"]
        + count_items(ct_snapshot_data, ct_grenade_df, "Decoy Grenade")
        * ITEM_PRICES["Decoy Grenade"]
    )
    features["t_utility_value"] = (
        features["t_smoke_count"] * ITEM_PRICES["Smoke Grenade"]
        + features["t_flash_count"] * ITEM_PRICES["Flashbang"]
        + features["t_he_count"] * ITEM_PRICES["High Explosive Grenade"]
        + count_items(t_snapshot_data, t_grenade_df, "Molotov") * ITEM_PRICES["Molotov"]
        + count_items(t_snapshot_data, t_grenade_df, "Incendiary Grenade")
        * ITEM_PRICES["Incendiary Grenade"]
        + count_items(t_snapshot_data, t_grenade_df, "Decoy Grenade")
        * ITEM_PRICES["Decoy Grenade"]
    )

    # ============================================
    # EQUIPMENT VALUE
    # ============================================

    features["ct_equipment_value"] = (
        features["ct_armor_count"] * ITEM_PRICES["Kevlar Vest"]
        + features["ct_helmet_count"] * 350
        + features["ct_defuser_count"] * ITEM_PRICES["Defuse Kit"]
        + features["ct_utility_value"]
        + count_all_weapon(ct_snapshot_data)
    )

    features["t_equipment_value"] = (
        features["t_armor_count"] * ITEM_PRICES["Kevlar Vest"]
        + features["t_helmet_count"] * 350
        + features["t_utility_value"]
        + count_all_weapon(t_snapshot_data)
    )

    features["ct_equipment_value_avg"] = features["ct_equipment_value"] / 5
    features["t_equipment_value_avg"] = features["t_equipment_value"] / 5

    # ============================================
    # CONTEXT
    # ============================================

    features["round_number"] = round_number
    features["ct_score"] = ct_score
    features["t_score"] = t_score

    # Detect side switches
    is_side_switch = (round_number == 13) or (
        round_number > 24 and (round_number - 25) % 3 == 0
    )

    # Streaks (reset at side switches)
    if is_side_switch or previous_round_data is None:
        features["ct_rounds_won_streak"] = 0
        features["ct_rounds_lost_streak"] = 0
        features["t_rounds_won_streak"] = 0
        features["t_rounds_lost_streak"] = 0
    else:
        if previous_round_data["round_winner"] == 1:  # CT won
            features["ct_rounds_won_streak"] = (
                1 + previous_round_data["ct_rounds_won_streak"]
            )
            features["ct_rounds_lost_streak"] = 0
        else:
            features["ct_rounds_won_streak"] = 0
            features["ct_rounds_lost_streak"] = (
                1 + previous_round_data["ct_rounds_lost_streak"]
            )

        if previous_round_data["round_winner"] == 0:  # T won
            features["t_rounds_won_streak"] = (
                1 + previous_round_data["t_rounds_won_streak"]
            )
            features["t_rounds_lost_streak"] = 0
        else:
            features["t_rounds_won_streak"] = 0
            features["t_rounds_lost_streak"] = (
                1 + previous_round_data["t_rounds_lost_streak"]
            )

    features["map_name"] = map_name
    features["is_overtime"] = 1 if round_number > 24 else 0

    # ============================================
    # EQUIPMENT SAVED (previous round)
    # ============================================

    if previous_last_tick_data is not None and not is_side_switch:
        features["ct_survivors_previous"] = previous_last_tick_data[
            previous_last_tick_data["team_side"] == "CT"
        ].shape[0]
        features["t_survivors_previous"] = previous_last_tick_data[
            previous_last_tick_data["team_side"] == "T"
        ].shape[0]
        features["ct_equipment_saved_value"] = previous_last_tick_data.loc[
            previous_last_tick_data["team_side"] == "CT", "current_equip_value"
        ].sum()
        features["t_equipment_saved_value"] = previous_last_tick_data.loc[
            previous_last_tick_data["team_side"] == "T", "current_equip_value"
        ].sum()
    else:
        features["ct_survivors_previous"] = 0
        features["t_survivors_previous"] = 0
        features["ct_equipment_saved_value"] = 0
        features["t_equipment_saved_value"] = 0

    # ============================================
    # TARGET
    # ============================================

    features["round_winner"] = round_winner

    return features


# ============================================
# DEMO PARSING FUNCTION
# ============================================


def parse_demo(demo_path):
    """
    Parse a single CS2 demo and extract features for all rounds.

    Args:
        demo_path: Path to .dem file

    Returns:
        pd.DataFrame: DataFrame with one row per round
    """

    print(f"Parsing: {demo_path.name}")

    # Initialize parsers
    demparser = DemoParser(str(demo_path))
    demawpy = Demo(str(demo_path))

    # parse demo
    demawpy.parse()

    # Get round metadata
    round_ticks = demawpy.rounds.to_pandas()[
        ["round_num", "start", "official_end", "winner", "freeze_end"]
    ]
    round_ticks = round_ticks.set_index("round_num")

    map_name = demawpy.header["map_name"]

    # Feature columns for parsing
    start_features = [
        "tick",
        "name",
        "team_name",
        "balance",
        "current_equip_value",
        "team_rounds_total",
    ]
    snapshot_features = [
        "tick",
        "name",
        "team_name",
        "inventory",
        "armor_value",
        "has_helmet",
        "has_defuser",
        "balance",
        "current_equip_value",
    ]
    last_tick_features = [
        "tick",
        "name",
        "team_name",
        "current_equip_value",
        "is_alive",
    ]

    rows = []
    previous_round_data = None
    previous_last_tick_data = None

    for round_num in round_ticks.index:

        # Get ticks
        start_tick = round_ticks.loc[round_num, "start"]
        freeze_tick = round_ticks.loc[round_num, "freeze_end"]
        snapshot_tick = freeze_tick + 2 * 128  # 2 seconds after freeze-time
        official_end_tick = round_ticks.loc[round_num, "official_end"]

        # Extract grenade data
        grenade_df = build_grenade_df(
            demawpy, start_tick=freeze_tick + 1, end_tick=snapshot_tick
        )

        # Parse ticks
        start_data = demparser.parse_ticks(start_features, ticks=[start_tick])
        start_data["team_side"] = start_data["team_name"].map(
            {"CT": "CT", "TERRORIST": "T"}
        )

        snapshot_data = demparser.parse_ticks(snapshot_features, ticks=[snapshot_tick])
        snapshot_data["team_side"] = snapshot_data["team_name"].map(
            {"CT": "CT", "TERRORIST": "T"}
        )

        # Get scores
        score_by_side = start_data.groupby("team_side")["team_rounds_total"].first()
        ct_score = score_by_side.get("CT", 0)
        t_score = score_by_side.get("T", 0)

        # Get round winner
        w = round_ticks.loc[round_num, "winner"]
        w = str(w).strip().lower()
        round_winner = 1 if w == "ct" else 0  # 1=CT, 0=T

        # Extract features
        features = extract_round_features(
            start_data,
            round_num,
            snapshot_data,
            grenade_df,
            map_name,
            ct_score,
            t_score,
            round_winner,
            previous_round_data=previous_round_data,
            previous_last_tick_data=previous_last_tick_data,
        )

        rows.append(features)

        # Update previous round data
        previous_round_data = features

        previous_last_tick_data = demparser.parse_ticks(
            last_tick_features, ticks=[official_end_tick - 1]
        )
        previous_last_tick_data["team_side"] = previous_last_tick_data["team_name"].map(
            {"CT": "CT", "TERRORIST": "T"}
        )
        previous_last_tick_data = previous_last_tick_data[
            previous_last_tick_data["is_alive"] == True
        ]

    df = pd.DataFrame(rows)

    print(f"✓ Extracted {len(df)} rounds from {demo_path.name}")

    return df
