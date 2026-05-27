"""
parser.py — Parse CS2 demo files and extract round-level features.

For every round of a given demo, captures the state at freeze_end + 2s
(money, equipment, weapons, utility, armour, survivors, streaks, plant
flag) for both teams and returns one row per round. Combines awpy (for
the round/grenade/bomb tables) and demoparser2 (for per-tick state).
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
    "MP7": 1400,
    "MP5-SD": 1400,
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


LOSS_BONUS = {0: 1400, 1: 1900, 2: 2400, 3: 2900, 4: 3400}


# ============================================
# HELPER FUNCTIONS
# ============================================


def count_weapon(snapshot_data, weapon):

    if isinstance(weapon, str):
        weapons = [weapon]
    else:
        weapons = list(weapon)

    inv = snapshot_data["inventory"]
    inv_series = inv.explode()

    return inv_series.isin(weapons).sum()


def count_all_weapon(snapshot_data):

    total_value = 0

    for weapon, price in ALL_WEAPON_DICT.items():
        count = count_weapon(snapshot_data, weapon)
        total_value += count * price

    return total_value


def count_items(snapshot_data, grenade_df, item):

    if isinstance(item, str):
        items = {item}
    else:
        items = set(item)

    max_per_player = 2 if "Flashbang" in items else 1

    if grenade_df is not None and not grenade_df.empty:
        thrown_by_player = (
            grenade_df[grenade_df["grenade_type"].isin(items)].groupby("thrower").size()
        )
    else:
        thrown_by_player = pd.Series(dtype=int)

    total = 0
    for _, player in snapshot_data.iterrows():
        inv = player["inventory"]
        inv_count = sum(1 for x in inv if x in items) if isinstance(inv, list) else 0
        player_thrown = thrown_by_player.get(player["name"], 0)
        total += min(inv_count + player_thrown, max_per_player)

    return int(total)


def build_grenade_df(demawpy, start_tick, end_tick):

    g = demawpy.grenades.to_pandas().copy()

    # Keep grenades thrown within the snapshot window only
    g = g[(g["tick"] > start_tick) & (g["tick"] <= end_tick)].copy()
    if g.empty:
        return pd.DataFrame(columns=["tick", "thrower", "grenade_type"])

    # Keep grenades that have XYZ coordinates (i.e. actually thrown, not buffered)
    pos_mask = g[["X", "Y", "Z"]].notna().all(axis=1)
    g = g[pos_mask].copy()
    if g.empty:
        return pd.DataFrame(columns=["tick", "thrower", "grenade_type"])

    g = g.sort_values("tick").drop_duplicates(subset=["entity_id"], keep="first").copy()

    # Normalize grenade names
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
    awpy_round_num=None,
):

    features = {}

    ct_start_data = start_tick_data[start_tick_data["team_side"] == "CT"]
    t_start_data = start_tick_data[start_tick_data["team_side"] == "T"]

    ct_snapshot_data = snapshot_data[snapshot_data["team_side"] == "CT"]
    t_snapshot_data = snapshot_data[snapshot_data["team_side"] == "T"]

    ct_names = set(ct_snapshot_data["name"])
    t_names = set(t_snapshot_data["name"])

    ct_team_name = ct_start_data["team_clan_name"].dropna().iloc[0]
    t_team_name = t_start_data["team_clan_name"].dropna().iloc[0]

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
    # NAMES
    # ============================================

    features["ct_team_name"] = ct_team_name
    features["t_team_name"] = t_team_name

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

    features["ct_armor_count"] = (ct_snapshot_data["armor_value"] > 0).sum()
    features["t_armor_count"] = (t_snapshot_data["armor_value"] > 0).sum()

    features["ct_helmet_count"] = (ct_snapshot_data["has_helmet"]).sum()
    features["t_helmet_count"] = (t_snapshot_data["has_helmet"]).sum()

    features["ct_defuser_count"] = (ct_snapshot_data["has_defuser"]).sum()

    # ============================================
    # ARMEMENT
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

    # ============================================
    # CONTEXT
    # ============================================

    features["round_number"] = round_number
    features["ct_score"] = ct_score
    features["t_score"] = t_score

    # Detect side switches using awpy's original round number (unaffected by skipped rounds)
    rn = awpy_round_num if awpy_round_num is not None else round_number
    is_side_switch = (rn == 13) or (rn > 24 and (rn - 25) % 3 == 0)

    # Streaks
    if is_side_switch or previous_round_data is None:
        features["ct_rounds_won_streak"] = 0
        features["t_rounds_won_streak"] = 0
    else:
        if previous_round_data["round_winner"] == 1:  # CT won
            features["ct_rounds_won_streak"] = (
                1 + previous_round_data["ct_rounds_won_streak"]
            )
        else:
            features["ct_rounds_won_streak"] = 0

        if previous_round_data["round_winner"] == 0:  # T won
            features["t_rounds_won_streak"] = (
                1 + previous_round_data["t_rounds_won_streak"]
            )
        else:
            features["t_rounds_won_streak"] = 0

    features["map_name"] = map_name
    features["is_overtime"] = 1 if rn > 24 else 0

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

    print(f"Parsing: {demo_path.name}")

    demparser = DemoParser(str(demo_path))
    demawpy = Demo(str(demo_path))

    demawpy.parse()

    round_ticks = demawpy.rounds.to_pandas()[
        ["round_num", "start", "official_end", "winner", "freeze_end"]
    ]
    round_ticks = round_ticks.set_index("round_num")

    # Set of awpy round_num where the bomb was planted.
    # demawpy.bomb has events {pickup, drop, plant, defuse, detonate} — we want only plants.
    # round_num in demawpy.bomb is aligned with round_ticks.index (same awpy numbering),
    # so no tick-to-round mapping is needed.
    try:
        import polars as pl

        _plant_rounds_set = set(
            demawpy.bomb.filter(pl.col("event") == "plant")["round_num"].to_list()
        )
    except Exception:
        _plant_rounds_set = set()

    map_name = demawpy.header["map_name"]

    start_features = [
        "tick",
        "name",
        "team_name",
        "team_clan_name",
        "balance",
        "current_equip_value",
    ]
    snapshot_features = [
        "tick",
        "name",
        "team_name",
        "team_clan_name",
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
        "team_clan_name",
        "current_equip_value",
        "is_alive",
    ]

    rows = []
    previous_round_data = None
    previous_last_tick_data = None
    ct_score = 0
    t_score = 0

    ct_loss_count = 1
    t_loss_count = 1

    prev_bomb_planted = 0

    skipped_rounds = 0

    for round_num in round_ticks.index:

        start_tick = round_ticks.loc[round_num, "start"]
        freeze_tick = round_ticks.loc[round_num, "freeze_end"]
        official_end_tick = int(round_ticks.loc[round_num, "official_end"])

        if pd.isna(freeze_tick):
            # Check if this is a real round (demo starts at freeze_end)
            # by looking at player money at start_tick
            test_data = demparser.parse_ticks(start_features, ticks=[int(start_tick)])
            if test_data.empty or "team_name" not in test_data.columns:
                skipped_rounds += 1
                continue
            test_data["team_side"] = test_data["team_name"].map(
                {"CT": "CT", "TERRORIST": "T"}
            )
            total_money = (
                test_data["balance"].sum() + test_data["current_equip_value"].sum()
            )
            if total_money > 12000:
                # Not a pistol round — likely warmup/knife, skip it
                skipped_rounds += 1
                continue
            # Real round where demo starts at freeze — use start_tick as snapshot
            freeze_tick = int(start_tick)
            snapshot_tick = freeze_tick
            grenade_df = None  # No grenades thrown yet
        else:
            freeze_tick = int(freeze_tick)
            snapshot_tick = freeze_tick + 2 * 128  # 2 seconds after freeze-time
            grenade_df = build_grenade_df(
                demawpy, start_tick=freeze_tick + 1, end_tick=snapshot_tick
            )

        start_data = demparser.parse_ticks(start_features, ticks=[start_tick])
        if start_data.empty or "team_name" not in start_data.columns:
            print(
                f"  Skipping round {round_num}: empty start_data at tick {start_tick}"
            )
            continue
        start_data["team_side"] = start_data["team_name"].map(
            {"CT": "CT", "TERRORIST": "T"}
        )

        snapshot_data = demparser.parse_ticks(snapshot_features, ticks=[snapshot_tick])
        if snapshot_data.empty or "team_name" not in snapshot_data.columns:
            # Fallback: use freeze_end tick instead of snapshot_tick
            snapshot_data = demparser.parse_ticks(
                snapshot_features, ticks=[freeze_tick]
            )
            if snapshot_data.empty or "team_name" not in snapshot_data.columns:
                print(f"  Skipping round {round_num}: empty snapshot_data")
                continue
            grenade_df = None  # No grenades thrown yet at freeze_end
        snapshot_data["team_side"] = snapshot_data["team_name"].map(
            {"CT": "CT", "TERRORIST": "T"}
        )

        w = round_ticks.loc[round_num, "winner"]
        w = str(w).strip().lower()
        round_winner = 1 if w == "ct" else 0  # 1=CT, 0=T

        # Use awpy's original round_num for side switch detection,
        # not the adjusted round_number (which is offset by skipped_rounds)
        adjusted_round_num = round_num - skipped_rounds

        # Reset loss_count at each side swap (R13 + OT half boundaries MR3)
        if adjusted_round_num == 13 or (
            adjusted_round_num >= 25 and (adjusted_round_num - 25) % 3 == 0
        ):
            ct_loss_count = 1
            t_loss_count = 1

        features = extract_round_features(
            start_data,
            adjusted_round_num,
            snapshot_data,
            grenade_df,
            map_name,
            ct_score,
            t_score,
            round_winner,
            previous_round_data=previous_round_data,
            previous_last_tick_data=previous_last_tick_data,
            awpy_round_num=round_num,
        )

        # Bomb-plant state for THIS round (from awpy.demo.bomb). Used only locally to
        # update prev_bomb_planted for the next iteration — NOT exposed in features.
        bomb_planted_this_round = int(round_num in _plant_rounds_set)

        # previous_bomb_planted: 1 if the bomb was planted in the previous round of
        # the same half, else 0. Forced to 0 at half boundaries (R1, R13, every OT
        # MR3 boundary R25/R28/R31...) since the economy is reset there.
        is_half_boundary = (
            adjusted_round_num == 1
            or adjusted_round_num == 13
            or (adjusted_round_num >= 25 and (adjusted_round_num - 25) % 3 == 0)
        )
        features["previous_bomb_planted"] = 0 if is_half_boundary else prev_bomb_planted

        # Update for the next iteration (after we've consumed the previous value)
        prev_bomb_planted = bomb_planted_this_round

        # Economic features driven by the loss_bonus table
        features["ct_loss_count"] = ct_loss_count
        features["t_loss_count"] = t_loss_count
        features["ct_loss_bonus"] = LOSS_BONUS[ct_loss_count]
        features["t_loss_bonus"] = LOSS_BONUS[t_loss_count]
        features["ct_cash_next_if_loss"] = (
            features["ct_cash"] + 5 * features["ct_loss_bonus"]
        )
        features["t_cash_next_if_loss"] = (
            features["t_cash"] + 5 * features["t_loss_bonus"]
        )

        rows.append(features)

        previous_round_data = features

        # Update score AFTER extracting features (score is state at round start)
        if round_winner == 1:
            ct_score += 1
        else:
            t_score += 1

        # Update loss_count for the NEXT round (same convention as the bonus table)
        if round_winner == 1:  # CT wins this round
            ct_loss_count = max(0, ct_loss_count - 1)
            t_loss_count = min(4, t_loss_count + 1)
        else:  # T wins this round
            ct_loss_count = min(4, ct_loss_count + 1)
            t_loss_count = max(0, t_loss_count - 1)

        previous_last_tick_data = demparser.parse_ticks(
            last_tick_features, ticks=[official_end_tick - 1]
        )
        if (
            previous_last_tick_data.empty
            or "team_name" not in previous_last_tick_data.columns
        ):
            previous_last_tick_data = None
        else:
            previous_last_tick_data["team_side"] = previous_last_tick_data[
                "team_name"
            ].map({"CT": "CT", "TERRORIST": "T"})
            previous_last_tick_data = previous_last_tick_data[
                previous_last_tick_data["is_alive"] == True
            ]

    df = pd.DataFrame(rows)

    print(f"  Extracted {len(df)} rounds from {demo_path.name}")

    return df
