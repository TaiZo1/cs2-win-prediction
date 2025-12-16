# BAD Project - CS2 Win Prediction

Analysis of professional CS2 matches using economic and tactical features extracted from demo files.

**Course**: Bases de l'Analyse de Données (BAD) - Sorbonne Université, Fall 2024

---

## What this does

**Input**: CS2 demo files (.dem) from professional HLTV matches  
**Processing**: Extract 51 economic/tactical features per round at freeze-time  
**Output**: Clean dataset ready for statistical analysis

**Current dataset**: 1,539 rounds (71 matches) from BLAST Austin Major 2025.

---

## Running the code

```bash
cd notebooks
jupyter notebook 01_data_collection.ipynb
```

1. Place `.dem` files in `data/raw/`
2. Run all cells
3. Output saved in `data/processed/all_matches.csv`

**Processing time**: ~30-60 seconds per demo

---

## Features extracted (51 total)

Each row = 1 round at freeze-time (t=15s + 2s buy phase)

- Team money totals and per-player averages
- Equipment values (weapons, armor, utility)
- Weapon counts (AWP, rifles, SMGs, heavy)
- Utility counts (smokes, flashes, molotovs, HE)
- Score differential and win/loss streaks
- Equipment saved from previous round
- Target: round_winner (0=T, 1=CT)

---

## Data quality validation

All features validated against demo playback:

**Automated checks**:
- Value ranges (money 0-80k, weapons 0-5)
- Score progression consistency
- Side switch handling (round 13, overtime)
- Streak resets at side switches

**Manual verification**:
- Round 1 pistol (4000 money, no rifles/AWP)
- Equipment values match actual gameplay
- Economic state progression is logical

---

## Technical notes

**Parsing**: demoparser2 + awpy  
**Snapshot timing**: freeze_end + 2 seconds (captures buy phase)  
**Side switches**: Handled at round 13 and every 3 rounds in overtime

**Important**: `ct_score` and `t_score` follow the side (CT/T), not team identity. Teams switch sides at halftime and in overtime.

---

## Planned analysis

Following BAD course curriculum:

- Descriptive statistics (distributions, correlations, tests)
- PCA (dimensionality reduction)
- Clustering (K-means, hierarchical)
- Baseline classification (KNN, Logistic Regression)

---

## Structure

```
bad/
├── notebooks/
│   └── 01_data_collection.ipynb    # Feature extraction
├── src/data/
│   └── parser.py                   # Parsing logic
├── data/
│   ├── raw/                        # .dem files (not versioned)
│   ├── interim/                    # Per-match CSVs
│   └── processed/                  # Final dataset
└── reports/                        # Analysis outputs
```

---

## Dependencies

See `requirements.txt` at repository root.

Core: pandas, numpy, demoparser2, awpy, scikit-learn
