from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STATS_DIR = DATA_DIR / "stats"
RAW_DIR = DATA_DIR / "raw"

# ──────────────────────────────────────────────────────────────────────
# All S-Tier CS2 tournaments from 2025 + first 3 played in 2026
# Keys = directory names (hyphenated), Values = HLTV event URLs
# Ordered chronologically
# ──────────────────────────────────────────────────────────────────────
TOURNAMENTS = {
    # ─── 2025 ────────────────────────────────────────────────────────
    "blast-bounty-2025-season-1-finals":   "https://www.hltv.org/events/7909/blast-bounty-2025-season-1-finals",         # Jan 14-19
    "iem-katowice-2025":                   "https://www.hltv.org/events/8034/iem-katowice-2025",                         # Jan 29 - Feb 9
    "pgl-cluj-napoca-2025":                "https://www.hltv.org/events/8043/pgl-cluj-napoca-2025",                      # Feb 14-23
    "esl-pro-league-season-21":            "https://www.hltv.org/events/8292/esl-pro-league-season-21",                  # Mar 1-16
    "blast-open-lisbon-2025":              "https://www.hltv.org/events/7904/blast-open-lisbon-2025",                    # Mar 19-30
    "pgl-bucharest-2025":                  "https://www.hltv.org/events/8044/pgl-bucharest-2025",                        # Apr 6-13
    "iem-melbourne-2025":                  "https://www.hltv.org/events/8036/iem-melbourne-2025",                        # Apr 21-27
    "blast-rivals-2025-season-1":          "https://www.hltv.org/events/7905/blast-rivals-2025-season-1",                # Apr 30 - May 4
    "pgl-astana-2025":                     "https://www.hltv.org/events/8045/pgl-astana-2025",                           # May 10-18
    "iem-dallas-2025":                     "https://www.hltv.org/events/8037/iem-dallas-2025",                           # May 19-25
    "blast-austin-major-2025":             "https://www.hltv.org/events/7902/blasttv-austin-major-2025",                 # Jun 3-22
    "iem-cologne-2025":                    "https://www.hltv.org/events/8038/iem-cologne-2025",                          # Jul 23 - Aug 3
    "blast-bounty-2025-season-2-finals":   "https://www.hltv.org/events/7910/blast-bounty-2025-season-2-finals",         # Aug 14-17
    "esports-world-cup-2025":              "https://www.hltv.org/events/8039/esports-world-cup-2025",                    # Aug 20-24
    "blast-open-london-2025":              "https://www.hltv.org/events/7907/blast-open-london-2025",                    # Sep 5-7
    "fissure-playground-2":                "https://www.hltv.org/events/8064/fissure-playground-2",                      # Sep 12-21
    "esl-pro-league-season-22":            "https://www.hltv.org/events/8040/esl-pro-league-season-22",                  # Sep 28 - Oct 12
    "iem-chengdu-2025":                    "https://www.hltv.org/events/8041/iem-chengdu-2025",                          # Nov 3-9
    "blast-rivals-2025-season-2":          "https://www.hltv.org/events/7908/blast-rivals-2025-season-2",                # Nov 12-16
    "starladder-budapest-major-2025":      "https://www.hltv.org/events/8042/starladder-budapest-major-2025",            # Nov 24 - Dec 14

    # ─── 2026 (first 3 played) ──────────────────────────────────────
    "blast-bounty-2026-season-1-finals":   "https://www.hltv.org/events/8246/blast-bounty-2026-season-1-finals",         # Jan 22-25
    "iem-krakow-2026":                     "https://www.hltv.org/events/8240/iem-krakw-2026",                            # Jan 28 - Feb 8
    "pgl-cluj-napoca-2026":                "https://www.hltv.org/events/8047/pgl-cluj-napoca-2026",                      # Feb 14-22
}
