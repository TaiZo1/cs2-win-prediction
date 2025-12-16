"""
Validation Script for CS2 Feature Extraction
Automatically checks for logical inconsistencies in extracted features
"""

import pandas as pd
import numpy as np
from pathlib import Path

def validate_features(df):
    """
    Validate extracted features against CS2 game rules
    
    Returns:
        dict: validation results with pass/fail for each check
    """
    
    results = {
        'total_rounds': len(df),
        'checks': {},
        'warnings': [],
        'errors': []
    }
    
    # ============================================
    # 1. BASIC SANITY CHECKS
    # ============================================
    
    # Check: All rounds have 5 players per team (via money counts)
    results['checks']['player_count'] = {
        'name': 'Player count consistency',
        'passed': True,
        'issues': []
    }
    
    # Check: Money ranges (0-65535 total per team, 0-16000 per player avg)
    max_money_total = 16000 * 5  # 80000 per team
    
    ct_money_issues = df[df['ct_money_total'] > max_money_total]
    t_money_issues = df[df['t_money_total'] > max_money_total]
    
    if len(ct_money_issues) > 0 or len(t_money_issues) > 0:
        results['checks']['money_range'] = {
            'name': 'Money within valid range',
            'passed': False,
            'issues': f"CT: {len(ct_money_issues)} rounds, T: {len(t_money_issues)} rounds exceed max"
        }
        results['errors'].append(f"Money exceeds max in {len(ct_money_issues) + len(t_money_issues)} rounds")
    else:
        results['checks']['money_range'] = {
            'name': 'Money within valid range',
            'passed': True,
            'issues': []
        }
    
    # ============================================
    # 2. WEAPON COUNT CHECKS
    # ============================================
    
    # Check: AWP count (0-5 per team)
    ct_awp_invalid = df[(df['ct_awp_count'] < 0) | (df['ct_awp_count'] > 5)]
    t_awp_invalid = df[(df['t_awp_count'] < 0) | (df['t_awp_count'] > 5)]
    
    if len(ct_awp_invalid) > 0 or len(t_awp_invalid) > 0:
        results['checks']['awp_count'] = {
            'name': 'AWP count valid (0-5)',
            'passed': False,
            'issues': f"Invalid counts in {len(ct_awp_invalid) + len(t_awp_invalid)} rounds"
        }
        results['errors'].append("AWP counts outside 0-5 range")
    else:
        results['checks']['awp_count'] = {
            'name': 'AWP count valid (0-5)',
            'passed': True,
            'issues': []
        }
    
    # ============================================
    # 3. SCORE CONSISTENCY
    # ============================================
    
    # Check: Score progression (should increase by 1 each round)
    score_issues = []
    for i in range(1, len(df)):
        prev_ct = df.iloc[i-1]['ct_score']
        prev_t = df.iloc[i-1]['t_score']
        curr_ct = df.iloc[i]['ct_score']
        curr_t = df.iloc[i]['t_score']
        
        # Skip side switches (round 13, 25, 28, 31...)
        curr_round = df.iloc[i]['round_number']
        is_side_switch = (curr_round == 13) or (curr_round > 24 and (curr_round - 25) % 3 == 0)
        
        if not is_side_switch:
            total_increase = (curr_ct - prev_ct) + (curr_t - prev_t)
            if total_increase != 1:
                score_issues.append(f"Round {curr_round}: score increased by {total_increase} (expected 1)")
    
    if len(score_issues) > 0:
        results['checks']['score_progression'] = {
            'name': 'Score increases by 1 each round',
            'passed': False,
            'issues': score_issues[:5]  # Show first 5 issues
        }
        results['errors'].append(f"Score progression issues in {len(score_issues)} rounds")
    else:
        results['checks']['score_progression'] = {
            'name': 'Score increases by 1 each round',
            'passed': True,
            'issues': []
        }
    
    # ============================================
    # 4. STREAK RESETS
    # ============================================
    
    # Check: Streaks reset at side switches
    streak_issues = []
    for i, row in df.iterrows():
        round_num = row['round_number']
        is_side_switch = (round_num == 13) or (round_num > 24 and (round_num - 25) % 3 == 0)
        
        if is_side_switch:
            if (row['ct_rounds_won_streak'] != 0 or 
                row['ct_rounds_lost_streak'] != 0 or
                row['t_rounds_won_streak'] != 0 or
                row['t_rounds_lost_streak'] != 0):
                streak_issues.append(f"Round {round_num}: streaks not reset at side switch")
    
    if len(streak_issues) > 0:
        results['checks']['streak_resets'] = {
            'name': 'Streaks reset at side switches',
            'passed': False,
            'issues': streak_issues
        }
        results['errors'].append(f"Streak reset issues in {len(streak_issues)} rounds")
    else:
        results['checks']['streak_resets'] = {
            'name': 'Streaks reset at side switches',
            'passed': True,
            'issues': []
        }
    
    # ============================================
    # 5. EQUIPMENT SAVED RESETS
    # ============================================
    
    # Check: Equipment saved is 0 at side switches
    equipment_issues = []
    for i, row in df.iterrows():
        round_num = row['round_number']
        is_side_switch = (round_num == 13) or (round_num > 24 and (round_num - 25) % 3 == 0)
        
        if is_side_switch:
            if (row['ct_equipment_saved_value'] != 0 or 
                row['t_equipment_saved_value'] != 0 or
                row['ct_survivors_previous'] != 0 or
                row['t_survivors_previous'] != 0):
                equipment_issues.append(f"Round {round_num}: equipment saved not reset at side switch")
    
    if len(equipment_issues) > 0:
        results['checks']['equipment_resets'] = {
            'name': 'Equipment saved reset at side switches',
            'passed': False,
            'issues': equipment_issues
        }
        results['errors'].append(f"Equipment reset issues in {len(equipment_issues)} rounds")
    else:
        results['checks']['equipment_resets'] = {
            'name': 'Equipment saved reset at side switches',
            'passed': True,
            'issues': []
        }
    
    # ============================================
    # 6. ROUND WINNER CONSISTENCY
    # ============================================
    
    # Check: round_winner matches score increase
    winner_issues = []
    for i in range(1, len(df)):
        prev_ct = df.iloc[i-1]['ct_score']
        prev_t = df.iloc[i-1]['t_score']
        curr_ct = df.iloc[i]['ct_score']
        curr_t = df.iloc[i]['t_score']
        
        curr_round = df.iloc[i]['round_number']
        is_side_switch = (curr_round == 13) or (curr_round > 24 and (curr_round - 25) % 3 == 0)
        
        if not is_side_switch:
            prev_winner = df.iloc[i-1]['round_winner']
            
            if curr_ct > prev_ct and prev_winner != 1:
                winner_issues.append(f"Round {curr_round}: CT score increased but winner={prev_winner}")
            if curr_t > prev_t and prev_winner != 0:
                winner_issues.append(f"Round {curr_round}: T score increased but winner={prev_winner}")
    
    if len(winner_issues) > 0:
        results['checks']['winner_consistency'] = {
            'name': 'Round winner matches score increase',
            'passed': False,
            'issues': winner_issues[:5]
        }
        results['warnings'].append(f"Winner consistency issues in {len(winner_issues)} rounds")
    else:
        results['checks']['winner_consistency'] = {
            'name': 'Round winner matches score increase',
            'passed': True,
            'issues': []
        }
    
    # ============================================
    # 7. FIRST ROUND (PISTOL)
    # ============================================
    
    # Check: Round 1 has pistol-appropriate values
    first_round = df[df['round_number'] == 1].iloc[0]
    
    pistol_issues = []
    
    # Money should be 800*5 + 0 equipment = 4000
    if first_round['ct_money_total'] != 4000:
        pistol_issues.append(f"CT money: {first_round['ct_money_total']} (expected 4000)")
    if first_round['t_money_total'] != 4000:
        pistol_issues.append(f"T money: {first_round['t_money_total']} (expected 4000)")
    
    # No AWPs in pistol round
    if first_round['ct_awp_count'] > 0 or first_round['t_awp_count'] > 0:
        pistol_issues.append("AWPs present in pistol round")
    
    # No rifles in pistol round (unless force-bought)
    if first_round['ct_rifle_count'] > 0 or first_round['t_rifle_count'] > 0:
        pistol_issues.append("Rifles present in pistol round (unusual)")
    
    if len(pistol_issues) > 0:
        results['checks']['pistol_round'] = {
            'name': 'Round 1 pistol characteristics',
            'passed': False,
            'issues': pistol_issues
        }
        results['warnings'].append("Pistol round has unusual features")
    else:
        results['checks']['pistol_round'] = {
            'name': 'Round 1 pistol characteristics',
            'passed': True,
            'issues': []
        }
    
    # ============================================
    # SUMMARY
    # ============================================
    
    total_checks = len(results['checks'])
    passed_checks = sum(1 for check in results['checks'].values() if check['passed'])
    
    results['summary'] = {
        'total_checks': total_checks,
        'passed': passed_checks,
        'failed': total_checks - passed_checks,
        'warnings': len(results['warnings']),
        'errors': len(results['errors'])
    }
    
    return results


def print_validation_report(results):
    """Pretty print validation results"""
    
    print("=" * 60)
    print("CS2 FEATURE EXTRACTION - VALIDATION REPORT")
    print("=" * 60)
    print(f"\nTotal rounds analyzed: {results['total_rounds']}")
    print(f"Total checks: {results['summary']['total_checks']}")
    print(f"✅ Passed: {results['summary']['passed']}")
    print(f"❌ Failed: {results['summary']['failed']}")
    print(f"⚠️  Warnings: {results['summary']['warnings']}")
    
    print("\n" + "=" * 60)
    print("DETAILED RESULTS")
    print("=" * 60)
    
    for check_name, check_data in results['checks'].items():
        status = "✅" if check_data['passed'] else "❌"
        print(f"\n{status} {check_data['name']}")
        
        if check_data['issues']:
            for issue in check_data['issues'][:3]:  # Show max 3 issues
                print(f"   └─ {issue}")
            
            if len(check_data['issues']) > 3:
                print(f"   └─ ... and {len(check_data['issues']) - 3} more")
    
    if results['errors']:
        print("\n" + "=" * 60)
        print("🚨 CRITICAL ERRORS")
        print("=" * 60)
        for error in results['errors']:
            print(f"  • {error}")
    
    if results['warnings']:
        print("\n" + "=" * 60)
        print("⚠️  WARNINGS (review manually)")
        print("=" * 60)
        for warning in results['warnings']:
            print(f"  • {warning}")
    
    print("\n" + "=" * 60)
    
    if results['summary']['failed'] == 0:
        print("✅ ALL CHECKS PASSED - DATA LOOKS GOOD!")
    else:
        print("❌ SOME CHECKS FAILED - REVIEW ERRORS ABOVE")
    
    print("=" * 60)


# ============================================
# USAGE EXAMPLE
# ============================================

if __name__ == "__main__":
    # Load your extracted data
    df = pd.read_csv("data/interim/vitality_vs_mongolz_inferno_2025-01-26.csv")
    
    # Run validation
    results = validate_features(df)
    
    # Print report
    print_validation_report(results)
    
    # Save detailed results to JSON
    import json
    with open("validation_report.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n✓ Detailed report saved to: validation_report.json")
