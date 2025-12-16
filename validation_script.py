"""
Validation Script for CS2 Feature Extraction
Automatically checks for logical inconsistencies in extracted features
Handles consolidated multi-match datasets
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json


def validate_features(df):
    """
    Validate extracted features against CS2 game rules

    Returns:
        dict: validation results with pass/fail for each check
    """

    results = {"total_rounds": len(df), "total_matches": df['match_file'].nunique(), "checks": {}, "warnings": [], "errors": []}

    # ============================================
    # 1. BASIC SANITY CHECKS
    # ============================================

    # Check: All rounds have 5 players per team (via money counts)
    results["checks"]["player_count"] = {
        "name": "Player count consistency",
        "passed": True,
        "issues": [],
    }

    # Check: Cash balance ranges (0-16000 per player, max 80000 per team)
    max_cash_total = 16000 * 5  # 80000 per team

    ct_cash_issues = df[df["ct_cash"] > max_cash_total]
    t_cash_issues = df[df["t_cash"] > max_cash_total]

    if len(ct_cash_issues) > 0 or len(t_cash_issues) > 0:
        results["checks"]["cash_range"] = {
            "name": "Cash within valid range (0-80k per team)",
            "passed": False,
            "issues": f"CT: {len(ct_cash_issues)} rounds, T: {len(t_cash_issues)} rounds exceed max",
        }
        results["errors"].append(
            f"Cash exceeds max in {len(ct_cash_issues) + len(t_cash_issues)} rounds"
        )
    else:
        results["checks"]["cash_range"] = {
            "name": "Cash within valid range (0-80k per team)",
            "passed": True,
            "issues": [],
        }

    # ============================================
    # 2. WEAPON COUNT CHECKS
    # ============================================

    # Check: AWP count (0-5 per team)
    ct_awp_invalid = df[(df["ct_awp_count"] < 0) | (df["ct_awp_count"] > 5)]
    t_awp_invalid = df[(df["t_awp_count"] < 0) | (df["t_awp_count"] > 5)]

    if len(ct_awp_invalid) > 0 or len(t_awp_invalid) > 0:
        results["checks"]["awp_count"] = {
            "name": "AWP count valid (0-5)",
            "passed": False,
            "issues": f"Invalid counts in {len(ct_awp_invalid) + len(t_awp_invalid)} rounds",
        }
        results["errors"].append("AWP counts outside 0-5 range")
    else:
        results["checks"]["awp_count"] = {
            "name": "AWP count valid (0-5)",
            "passed": True,
            "issues": [],
        }
    
    # Check: Rifle count (0-5 per team)
    ct_rifle_invalid = df[(df["ct_rifle_count"] < 0) | (df["ct_rifle_count"] > 5)]
    t_rifle_invalid = df[(df["t_rifle_count"] < 0) | (df["t_rifle_count"] > 5)]

    if len(ct_rifle_invalid) > 0 or len(t_rifle_invalid) > 0:
        results["checks"]["rifle_count"] = {
            "name": "Rifle count valid (0-5)",
            "passed": False,
            "issues": f"Invalid counts in {len(ct_rifle_invalid) + len(t_rifle_invalid)} rounds",
        }
        results["warnings"].append("Rifle counts outside 0-5 range")
    else:
        results["checks"]["rifle_count"] = {
            "name": "Rifle count valid (0-5)",
            "passed": True,
            "issues": [],
        }

    # ============================================
    # 3. SCORE CONSISTENCY (PER MATCH)
    # ============================================

    score_issues = []
    
    # Check each match separately
    for match_file, match_df in df.groupby('match_file'):
        match_df = match_df.sort_values('round_number').reset_index(drop=True)
        
        for i in range(1, len(match_df)):
            prev_ct = match_df.iloc[i - 1]["ct_score"]
            prev_t = match_df.iloc[i - 1]["t_score"]
            curr_ct = match_df.iloc[i]["ct_score"]
            curr_t = match_df.iloc[i]["t_score"]

            # Skip side switches (round 13, 25, 28, 31...)
            curr_round = match_df.iloc[i]["round_number"]
            is_side_switch = (curr_round == 13) or (
                curr_round > 24 and (curr_round - 25) % 3 == 0
            )

            if not is_side_switch:
                total_increase = (curr_ct - prev_ct) + (curr_t - prev_t)
                if total_increase != 1:
                    score_issues.append(
                        f"{match_file} Round {curr_round}: score increased by {total_increase} (expected 1)"
                    )
                    
                    if len(score_issues) >= 5:  # Limit to first 5 issues
                        break
        
        if len(score_issues) >= 5:
            break

    if len(score_issues) > 0:
        results["checks"]["score_progression"] = {
            "name": "Score increases by 1 each round (per match)",
            "passed": False,
            "issues": score_issues,
        }
        results["errors"].append(
            f"Score progression issues in {len(score_issues)} rounds"
        )
    else:
        results["checks"]["score_progression"] = {
            "name": "Score increases by 1 each round (per match)",
            "passed": True,
            "issues": [],
        }

    # ============================================
    # 4. STREAK RESETS
    # ============================================

    streak_issues = []
    for i, row in df.iterrows():
        round_num = row["round_number"]
        is_side_switch = (round_num == 13) or (
            round_num > 24 and (round_num - 25) % 3 == 0
        )

        if is_side_switch:
            if (
                row["ct_rounds_won_streak"] != 0
                or row["ct_rounds_lost_streak"] != 0
                or row["t_rounds_won_streak"] != 0
                or row["t_rounds_lost_streak"] != 0
            ):
                streak_issues.append(
                    f"{row['match_file']} Round {round_num}: streaks not reset at side switch"
                )
                
                if len(streak_issues) >= 5:
                    break

    if len(streak_issues) > 0:
        results["checks"]["streak_resets"] = {
            "name": "Streaks reset at side switches",
            "passed": False,
            "issues": streak_issues,
        }
        results["errors"].append(f"Streak reset issues in {len(streak_issues)} rounds")
    else:
        results["checks"]["streak_resets"] = {
            "name": "Streaks reset at side switches",
            "passed": True,
            "issues": [],
        }

    # ============================================
    # 5. EQUIPMENT SAVED RESETS
    # ============================================

    equipment_issues = []
    for i, row in df.iterrows():
        round_num = row["round_number"]
        is_side_switch = (round_num == 13) or (
            round_num > 24 and (round_num - 25) % 3 == 0
        )

        if is_side_switch:
            if (
                row["ct_equipment_saved_value"] != 0
                or row["t_equipment_saved_value"] != 0
                or row["ct_survivors_previous"] != 0
                or row["t_survivors_previous"] != 0
            ):
                equipment_issues.append(
                    f"{row['match_file']} Round {round_num}: equipment saved not reset at side switch"
                )
                
                if len(equipment_issues) >= 5:
                    break

    if len(equipment_issues) > 0:
        results["checks"]["equipment_resets"] = {
            "name": "Equipment saved reset at side switches",
            "passed": False,
            "issues": equipment_issues,
        }
        results["errors"].append(
            f"Equipment reset issues in {len(equipment_issues)} rounds"
        )
    else:
        results["checks"]["equipment_resets"] = {
            "name": "Equipment saved reset at side switches",
            "passed": True,
            "issues": [],
        }

    # ============================================
    # 6. ROUND WINNER CONSISTENCY (PER MATCH)
    # ============================================

    winner_issues = []
    
    for match_file, match_df in df.groupby('match_file'):
        match_df = match_df.sort_values('round_number').reset_index(drop=True)
        
        for i in range(1, len(match_df)):
            prev_ct = match_df.iloc[i - 1]["ct_score"]
            prev_t = match_df.iloc[i - 1]["t_score"]
            curr_ct = match_df.iloc[i]["ct_score"]
            curr_t = match_df.iloc[i]["t_score"]

            curr_round = match_df.iloc[i]["round_number"]
            is_side_switch = (curr_round == 13) or (
                curr_round > 24 and (curr_round - 25) % 3 == 0
            )

            if not is_side_switch:
                prev_winner = match_df.iloc[i - 1]["round_winner"]

                if curr_ct > prev_ct and prev_winner != 1:
                    winner_issues.append(
                        f"{match_file} Round {curr_round}: CT score increased but winner={prev_winner}"
                    )
                if curr_t > prev_t and prev_winner != 0:
                    winner_issues.append(
                        f"{match_file} Round {curr_round}: T score increased but winner={prev_winner}"
                    )
                    
                if len(winner_issues) >= 5:
                    break
        
        if len(winner_issues) >= 5:
            break

    if len(winner_issues) > 0:
        results["checks"]["winner_consistency"] = {
            "name": "Round winner matches score increase",
            "passed": False,
            "issues": winner_issues,
        }
        results["warnings"].append(
            f"Winner consistency issues in {len(winner_issues)} rounds"
        )
    else:
        results["checks"]["winner_consistency"] = {
            "name": "Round winner matches score increase",
            "passed": True,
            "issues": [],
        }

    # ============================================
    # 7. PISTOL ROUNDS (ALL MATCHES)
    # ============================================

    pistol_issues = []
    pistol_rounds = df[df["round_number"] == 1]

    for idx, first_round in pistol_rounds.iterrows():
        # Money total should be exactly 5000 (5 players × 800 + pistols/armor/utility)
        if first_round["ct_money_total"] != 5000:
            pistol_issues.append(
                f"{first_round['match_file']}: CT money {first_round['ct_money_total']} (expected 5000)"
            )
        if first_round["t_money_total"] != 5000:
            pistol_issues.append(
                f"{first_round['match_file']}: T money {first_round['t_money_total']} (expected 5000)"
            )

        # No AWPs in pistol round
        if first_round["ct_awp_count"] > 0 or first_round["t_awp_count"] > 0:
            pistol_issues.append(f"{first_round['match_file']}: AWPs present in pistol round")

        # No rifles in pistol round
        if first_round["ct_rifle_count"] > 0 or first_round["t_rifle_count"] > 0:
            pistol_issues.append(f"{first_round['match_file']}: Rifles present in pistol round")
        
        if len(pistol_issues) >= 5:
            break

    if len(pistol_issues) > 0:
        results["checks"]["pistol_round"] = {
            "name": "Pistol round characteristics",
            "passed": False,
            "issues": pistol_issues,
        }
        results["warnings"].append("Some pistol rounds have unusual features")
    else:
        results["checks"]["pistol_round"] = {
            "name": "Pistol round characteristics",
            "passed": True,
            "issues": [],
        }

    # ============================================
    # SUMMARY
    # ============================================

    total_checks = len(results["checks"])
    passed_checks = sum(1 for check in results["checks"].values() if check["passed"])

    results["summary"] = {
        "total_checks": total_checks,
        "passed": passed_checks,
        "failed": total_checks - passed_checks,
        "warnings": len(results["warnings"]),
        "errors": len(results["errors"]),
    }

    return results


def print_validation_report(results):
    """Pretty print validation results"""

    print("=" * 60)
    print("CS2 FEATURE EXTRACTION - VALIDATION REPORT")
    print("=" * 60)
    print(f"\nDataset: {results['total_matches']} matches, {results['total_rounds']} rounds")
    print(f"Total checks: {results['summary']['total_checks']}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    print(f"Warnings: {results['summary']['warnings']}")

    print("\n" + "=" * 60)
    print("DETAILED RESULTS")
    print("=" * 60)

    for check_name, check_data in results["checks"].items():
        status = "[PASS]" if check_data["passed"] else "[FAIL]"
        print(f"\n{status} {check_data['name']}")

        if check_data["issues"]:
            issues_to_show = check_data["issues"][:3] if isinstance(check_data["issues"], list) else [check_data["issues"]]
            
            for issue in issues_to_show:
                print(f"   └─ {issue}")

            if isinstance(check_data["issues"], list) and len(check_data["issues"]) > 3:
                print(f"   └─ ... and {len(check_data['issues']) - 3} more")

    if results["errors"]:
        print("\n" + "=" * 60)
        print("CRITICAL ERRORS")
        print("=" * 60)
        for error in results["errors"]:
            print(f"  - {error}")

    if results["warnings"]:
        print("\n" + "=" * 60)
        print("WARNINGS (review manually)")
        print("=" * 60)
        for warning in results["warnings"]:
            print(f"  - {warning}")

    print("\n" + "=" * 60)

    if results["summary"]["failed"] == 0:
        print("ALL CHECKS PASSED - DATA LOOKS GOOD!")
    else:
        print("SOME CHECKS FAILED - REVIEW ERRORS ABOVE")

    print("=" * 60)


# ============================================
# USAGE
# ============================================

if __name__ == "__main__":
    # Load consolidated dataset
    df = pd.read_csv("bad/data/processed/all_matches.csv")

    # Run validation
    results = validate_features(df)

    # Print report
    print_validation_report(results)

    # Save detailed results to JSON
    with open("validation_report.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n✓ Detailed report saved to: validation_report.json")
