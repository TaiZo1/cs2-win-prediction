# Predicting Round Winners in Counter-Strike 2

A data pipeline + exploratory analysis + classical modeling project, built end-to-end on professional CS2 matches. The goal: from the freeze-time state of a round (equipment, money, score, momentum, team-level statistics), predict which side will win.

> 1,511 Tier-1 matches • ~32,000 rounds • 2025–2026 tournaments

---

## Project at a glance

| Step | What it does | Code |
|------|--------------|------|
| **1. Parse demos** | Extract round-by-round game state from raw `.dem` replays. Snapshot taken at `freeze_end + 2s` (after all buys, before any duel). | `parsing/parser.py` |
| **2. Scrape HLTV** | Collect every team's historical statistics, broken down by map × side × time window × opponent tier, with strict date-cutoff to avoid leakage. | `scraping/` |
| **3. Clean & merge** | Concatenate per-map CSVs, fix phantom rounds, drop 4v5 pistols, split by round type, join HLTV stats, handle NaN. | `notebooks/01_clean_and_merge.ipynb` |
| **4. Explore** | Correlations, distributions, per-regime EDA on pistol / post-pistol / normal rounds. | `notebooks/02_eda.ipynb` |
| **5. Model** | PCA + logistic regression on each regime, with a temporal train/test split grouped by match. | `notebooks/03_modeling.ipynb` |

A LaTeX report summarising the analysis is in `report/`.

---

## Demo parsing (`parsing/parser.py`)

CS2 demos are deterministic binary recordings: every player position, inventory, money value, hit point and action is replayable tick by tick. We build the dataset by capturing **one row per round**, taken at `freeze_end + 2s` (≈ 256 ticks at 128 Hz). That window is the sweet spot: late buys and weapon pickups have settled, but no duel has occurred yet, so all ten players are still alive.

Two libraries are used together:
- **`demoparser2`** (Rust binding) — low-level access to per-tick state and individual events.
- **`awpy`** (Python, built on top of `demoparser2`) — pre-computed tables for rounds, grenades, bomb plants, map header.

For each round, the parser produces ~50 features:

| Family | Variables |
|---|---|
| Economy | `money_total`, `cash`, `equipment_value`, `utility_value`, `loss_count` |
| Weapons | `awp_count`, `rifle_count`, `smg_count`, `heavy_count`, `ak_count` (T) |
| Armour | `armor_count`, `helmet_count`, `defuser_count` (CT) |
| Utility | `smoke_count`, `flash_count`, `he_count`, `molo_count` |
| Context | `round_number`, `score`, `survivors_previous`, `previous_bomb_planted` |
| Momentum | `rounds_won_streak`, `rounds_lost_streak` |

Each variable is duplicated per side (`ct_*`, `t_*`). Two notable subtleties handled by the parser:
- **"Insta-smokes"**: smokes thrown in the first second of the round disappear from the player's inventory before the snapshot tick. The parser cross-references the inventory with the `awpy.grenades` table in the `[freeze_end, snapshot_tick]` window and caps the per-player total at the buy maximum (1 smoke/molo/HE, 2 flashes).
- **`previous_bomb_planted`**: computed natively from `awpy.demo.bomb`, with the flag shifted one round and forced to 0 at every half-time / side switch.

---

## HLTV scraping (`scraping/`)

HLTV.org publishes detailed team statistics for every professional team, but the data is fragmented across dozens of filter combinations. For each target tournament, the scraper walks three page types:

- the **event page** (tournament name, dates, map pool, list of matches);
- each **match result page** (official scores, demo download link);
- each **team statistics page**.

Team statistics are collected along a 4-dimensional grid:

| Dimension | Values |
|---|---|
| **Map** | Mirage, Inferno, Dust2, Nuke, Ancient, Train, Anubis, Overpass, *or* `global` (all-maps aggregate) |
| **Side** | CT, T, both |
| **Time window** | 30 days, 90 days, 6 months |
| **Opponent tier** | Top 5, Top 10, Top 20, Top 30, Top 50 |

For every match-map, the correct opponent tier is read from HLTV's own `matches.json`. From the resulting grid we extract the main indicators (rating, ADR, round-win %, flash-assists, pistol-win %, round-2 conversion, …).

**Leakage protection**: statistics scraped for a match played on day `D` are limited to `endDate = D - 1`, so the match we are predicting is never included in the historical stats fed to the model.

**Tier propagation**: HLTV doesn't always publish every combination. Top 5 data fills Top 10 if missing, which fills Top 20, and so on down to Top 50. The fallback never goes the other way around (filling Top 5 with Top 20 data would paint a falsely optimistic picture).

**NaN handling** (in `01_clean_and_merge.ipynb`):
1. **map → global**: replace a missing map-specific value by the all-maps value of the same team, same side, same window.
2. **cross-window**: fall back to 90d then 6months if 30d is missing.
3. **expanding median by date**: median over all past matches (no leakage).

---

## Splitting into three regimes

Pistol, post-pistol and normal rounds follow fundamentally different economic dynamics. Training a single model on the three would mix three different distributions. The dataset is therefore split at join time:

| Split | Rounds | Columns | CT win rate |
|---|---|---|---|
| `df_pistol`       |  2,945 |  70 | 50.5 % |
| `df_post_pistol`  |  2,956 | 105 | 52.3 % |
| `df_normal`       | 26,322 | 106 | 51.1 % |

---

## Modeling and key findings

Three logistic regressions are trained (one per regime), with a temporal train/test split grouped by match (the most recent 20 % of matches form the test set). Four nested feature configurations are compared (A = round-state only, B = +HLTV, C = +map, D = + quasi-target features for control).

| Regime       | Best AUC (test) | Best accuracy |
|--------------|:----:|:----:|
| Pistol       | ~0.56 | ~0.51 |
| Normal       | ~0.71 | ~0.64 |
| Post-pistol  | ~0.86 | ~0.78 |

Three takeaways:
1. **The round type is the strongest predictor of predictability.** Pistol rounds stay barely above chance; post-pistol rounds are almost deterministic.
2. **The immediate round state is the dominant signal.** Adding HLTV stats or map identity gains at most +0.01 AUC over the round-state baseline on normal and post-pistol rounds.
3. **PCA does not yield a useful dimensionality reduction.** 10–12 components are needed to capture 80 % of inertia across the three regimes, so we keep the full feature set for the regression.

---

## Project structure

```
cs2-win-prediction/
├── README.md
├── LICENSE
├── requirements.txt
├── data/                            # CSVs are not committed — see "Data" below
├── parsing/
│   └── parser.py                    # Demo -> per-map CSV
├── scraping/
│   ├── tournament_scraper.py        # Single-tournament scraper
│   ├── config.py                    # Tournament URLs + paths
│   └── run_all.py                   # Batch runner (sequential / parallel)
├── notebooks/
│   ├── 01_clean_and_merge.ipynb     # Clean rounds + join HLTV stats
│   ├── 02_eda.ipynb                 # Exploratory data analysis
│   └── 03_modeling.ipynb            # PCA + logistic regression
└── report/
    ├── main.tex                     # 5-page report (with appendices)
    ├── sections/
    └── figures/
```

---

## Data

CSV files are **not committed** (the raw `.dem` files weigh hundreds of GB, the per-map CSVs and HLTV scrape are large too). To reproduce the dataset, run the pipeline from scratch:

```bash
# 1. Scrape HLTV stats and download demos (long — several hours per tournament)
python scraping/run_all.py -p 2

# 2. Parse demos -> per-map CSVs
#    (write a driver around parsing/parser.py::parse_demo)

# 3. Clean and merge -> three final dataframes
jupyter nbconvert --to notebook --execute notebooks/01_clean_and_merge.ipynb
```

This produces `data/processed/df_pistol.csv`, `data/processed/df_post_pistol.csv`, `data/processed/df_normal.csv`, ready for `02_eda.ipynb` and `03_modeling.ipynb`.

---

## Setup

```bash
git clone https://github.com/TaiZo1/cs2-win-prediction.git
cd cs2-win-prediction
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For the parsing/scraping steps, install the extra dependencies listed at the top of `requirements.txt`.

---

## Author

Lucas Lacharme — [github.com/TaiZo1](https://github.com/TaiZo1)

## License

MIT — see [`LICENSE`](LICENSE).
