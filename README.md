# CS2 Win Prediction

Feature extraction and statistical analysis of professional Counter-Strike 2 matches using economic and tactical data from HLTV demos.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)

---

## Overview

This project builds a clean dataset from professional CS2 demos by extracting 51 economic and tactical features at the beginning of each round (freeze-time). The dataset enables statistical analysis of how team economic state influences round outcomes.

**Status**: Data collection pipeline complete and validated. Exploratory analysis in progress.

---

## What you get

**Input**: CS2 demo files (.dem) from HLTV  
**Output**: Round-level dataset with 51 features per observation  
**Format**: CSV ready for statistical analysis

Run the notebook → get `all_matches.csv` with:
- Team money and equipment values
- Weapon distribution (AWPs, rifles, SMGs)
- Utility spending (smokes, flashes, molotovs)
- Score differential and momentum indicators
- Validated against actual gameplay

---

## Quick start

```bash
git clone https://github.com/yourusername/cs2-economic-analysis.git
cd cs2-economic-analysis

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Add demo files to bad/data/raw/
cd bad/notebooks
jupyter notebook 01_data_collection.ipynb
```

**See [`bad/README.md`](bad/README.md) for detailed usage and feature descriptions.**

---

## Data quality

All extracted features validated through:
- Automated range checks (money, weapon counts, scores)
- Manual verification against demo playback
- Side switch handling (round 13, overtime)

Dataset is clean, reproducible, and ready for analysis.

---

## Project structure

```
cs2-economic-analysis/
├── bad/                 # Data collection & analysis (current)
│   ├── notebooks/       # Feature extraction
│   ├── src/data/       # Parsing modules
│   └── data/           # Raw demos → processed dataset
└── bas/                 # Future: advanced models, deployment
```

**Current work**: See `bad/` for the complete data pipeline and analysis.

---

## Technical stack

Python 3.11, pandas, demoparser2, awpy, Jupyter

Full dependencies in `requirements.txt`.

---

## Roadmap

**Phase 1 (current)**: Data collection and exploratory analysis  
**Phase 2 (upcoming)**: Advanced modeling and deployment

This project is developed as part of the Applied Mathematics curriculum at Sorbonne Université (M1).

---

## Contact

Lucas Lachaume  
M1 Applied Mathematics - Sorbonne Université  
[lacharme.lucas@gmail.com](mailto:lacharme.lucas@gmail.com) | [LinkedIn](https://linkedin.com/in/lucaslchrm)

---

## License

MIT License - see [LICENSE](LICENSE) file for details.
