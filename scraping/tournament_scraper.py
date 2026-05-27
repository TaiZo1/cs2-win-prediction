"""
HLTV CS2 Tournament Scraper

Scrapes team stats, player stats, match schedules, H2H stats, and demo files
for a CS2 tournament — all from a single HLTV event URL.

Auto-extracts tournament name, dates, map pool, and event ID from the page.

Date logic: match on date D uses stats endDate = D-1 (excludes the match itself).

Propagation rules for team stats:
    Top20 data fills down to Top30/Top50 if those are empty.
    Top30 data fills down to Top50 if empty.
    Never propagates upward (Top10 -> Top5 stays N/A).
"""

import csv
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By


MAP_ABBREV = {
    "inf": "de_inferno",
    "d2": "de_dust2",
    "mrg": "de_mirage",
    "anc": "de_ancient",
    "nuke": "de_nuke",
    "trn": "de_train",
    "anb": "de_anubis",
}

MAP_FULLNAME = {
    "Inferno": "de_inferno",
    "Dust2": "de_dust2",
    "Mirage": "de_mirage",
    "Ancient": "de_ancient",
    "Nuke": "de_nuke",
    "Train": "de_train",
    "Anubis": "de_anubis",
    "Overpass": "de_overpass",
    "Vertigo": "de_vertigo",
}

WINDOWS = {"30d": 30, "90d": 90, "6months": 180}
TOPS = ["Top5", "Top10", "Top20", "Top30", "Top50"]

TEAM_COLUMNS = [
    "map",
    "side",
    "top",
    "rating",
    "rw_pct",
    "opk_pct",
    "multik",
    "pct5v4",
    "pct4v5",
    "traded_pct",
    "adr",
    "fa",
    "pistol_win_pct",
    "round2_conv",
    "round2_break",
]

MAIN_STATS = [
    "rating_30",
    "rating_t",
    "rating_ct",
    "round_swing",
    "dpr",
    "kast",
    "multikill",
    "adr",
    "kpr",
]

DETAILED_STAT_MAP = {
    "Kills per round": "kills_per_round",
    "Rounds with a kill": "rounds_with_kill_pct",
    "Kills per round win": "kills_per_round_win",
    "Rating 3.0": "rating_30_side",
    "Damage per round": "damage_per_round",
    "Rounds with a multi-kill": "rounds_with_multikill_pct",
    "Damage per round win": "damage_per_round_win",
    "Pistol round rating": "pistol_round_rating",
    "Saved by teammate per round": "saved_by_teammate_per_round",
    "Traded deaths per round": "traded_deaths_per_round",
    "Traded deaths percentage": "traded_deaths_pct",
    "Opening deaths traded percentage": "opening_deaths_traded_pct",
    "Assists per round": "assists_per_round",
    "Support rounds": "support_rounds_pct",
    "Saved teammate per round": "saved_teammate_per_round",
    "Trade kills per round": "trade_kills_per_round",
    "Trade kills percentage": "trade_kills_pct",
    "Assisted kills percentage": "assisted_kills_pct",
    "Damage per kill": "damage_per_kill",
    "Opening kills per round": "opening_kills_per_round",
    "Opening deaths per round": "opening_deaths_per_round",
    "Opening attempts": "opening_attempts_pct",
    "Opening success": "opening_success_pct",
    "Win% after opening kill": "win_pct_after_opening_kill",
    "Attacks per round": "attacks_per_round",
    "Clutch points per round": "clutch_points_per_round",
    "Last alive percentage": "last_alive_pct",
    "1on1 win percentage": "1on1_win_pct",
    "Time alive per round": "time_alive_per_round",
    "Saves per round loss": "saves_per_round_loss",
    "Sniper kills per round": "sniper_kills_per_round",
    "Sniper kills percentage": "sniper_kills_pct",
    "Rounds with sniper kills percentage": "rounds_with_sniper_kills_pct",
    "Sniper multi-kill rounds": "sniper_multikill_rounds",
    "Sniper opening kills per round": "sniper_opening_kills_per_round",
    "Utility damage per round": "utility_damage_per_round",
    "Utility kills per 100 rounds": "utility_kills_per_100_rounds",
    "Flashes thrown per round": "flashes_thrown_per_round",
    "Flash assists per round": "flash_assists_per_round",
    "Time opponent flashed per round": "time_opponent_flashed_per_round",
}
DETAILED_COLUMNS = list(DETAILED_STAT_MAP.values())

GENERAL_STAT_MAP = {
    "Total kills": "total_kills",
    "Headshot %": "headshot_pct",
    "Total deaths": "total_deaths",
    "K/D Ratio": "kd_ratio",
    "Damage / Round": "damage_per_round_gen",
    "Grenade dmg / Round": "grenade_dmg_per_round",
    "Maps played": "maps_played",
    "Rounds played": "rounds_played",
    "Kills / round": "kills_per_round_gen",
    "Assists / round": "assists_per_round_gen",
    "Deaths / round": "deaths_per_round",
    "Saved by teammate / round": "saved_by_teammate_per_round_gen",
    "Saved teammates / round": "saved_teammates_per_round",
    "Impact rating": "impact_rating",
}
GENERAL_COLUMNS = list(GENERAL_STAT_MAP.values())

FEATURED_COLUMNS = [
    "rating_vs_top5",
    "rating_vs_top10",
    "rating_vs_top20",
    "rating_vs_top30",
    "rating_vs_top50",
]

PLAYER_COLUMNS = (
    ["map", "side", "top"]
    + MAIN_STATS
    + DETAILED_COLUMNS
    + GENERAL_COLUMNS
    + FEATURED_COLUMNS
)

H2H_COLUMNS = [
    "match_id",
    "date",
    "team1",
    "team2",
    "team1_h2h_wins",
    "team2_h2h_wins",
    "h2h_overtimes",
    "map",
    "team1_map_wins",
    "team2_map_wins",
    "team1_map_rounds",
    "team2_map_rounds",
]

RATING_STAT_LABELS = {
    "Rating 3.0": "rating",
}

FTU_STAT_LABELS = {
    "Round win %": "rw_pct",
    "Opening kill %": "opk_pct",
    "Multi-kill round": "multik",
    "5v4 won %": "pct5v4",
    "4v5 won %": "pct4v5",
    "Traded death %": "traded_pct",
    "ADR": "adr",
    "Flash assists / round": "fa",
}

PISTOL_STAT_LABELS = {
    "Pistol round win %": "pistol_win_pct",
    "Converted round 2 after won pistol %": "round2_conv",
    "Break round 2 after lost pistol %": "round2_break",
}

# 7-Zip path (Windows default)
SEVENZ = r"C:\Program Files\7-Zip\7z.exe"

# Demo map names for filename detection
DEMO_MAP_NAMES = [
    "anubis",
    "nuke",
    "dust2",
    "mirage",
    "train",
    "inferno",
    "ancient",
    "overpass",
    "vertigo",
]


class TournamentScraper:
    """Scrapes HLTV team/player stats, H2H, and demos for a CS2 tournament.

    Usage:
        scraper = TournamentScraper(
            event_url="https://www.hltv.org/events/7909/blast-bounty-2025-season-1-finals",
            output_dir="data/blast_bounty_2025",
        )
        scraper.scrape_tournament()
    """

    def __init__(self, event_url, output_dir, demo_dir=None):
        self.event_url = event_url.rstrip("/")
        self.output_dir = Path(output_dir)
        self.demo_dir = Path(demo_dir) if demo_dir else None
        self.driver = None

        # Auto-extracted from page
        self.event_id = None
        self.tournament_name = None
        self.start_date = None
        self.end_date = None
        self.map_pool = []
        self.dates = []

        # Populated during scraping
        self.tournament_teams = []
        self.players_by_team = {}

        # Extract event_id from URL immediately
        m = re.search(r"/events/(\d+)/", self.event_url)
        if m:
            self.event_id = int(m.group(1))

    # ─── Utilities ────────────────────────────────────────────────────

    @staticmethod
    def _date_minus(date_str, days):
        dt = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=days)
        return dt.strftime("%Y-%m-%d")

    @staticmethod
    def _parse_val(text):
        text = text.strip()
        if not text or text in ("-", "N/A"):
            return ""
        if "m " in text and "s" in text:
            return text
        text = text.replace("%", "")
        try:
            return float(text)
        except ValueError:
            return text

    @staticmethod
    def _slugify(name):
        """Convert team name to filename-safe slug."""
        return name.lower().replace(" ", "-").replace(".", "").replace("'", "")

    def _init_driver(self):
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=en-US")

        if self.demo_dir:
            temp_dl = self.output_dir / "_temp_downloads"
            temp_dl.mkdir(parents=True, exist_ok=True)
            prefs = {
                "download.default_directory": str(temp_dl),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
            }
            options.add_experimental_option("prefs", prefs)

        self.driver = uc.Chrome(options=options, version_main=145)

    def _dismiss_cookie(self):
        try:
            self.driver.find_element(
                By.ID, "CybotCookiebotDialogBodyButtonDecline"
            ).click()
            time.sleep(0.5)
        except Exception:
            pass
        try:
            self.driver.execute_script(
                """
                var el = document.getElementById('CybotCookiebotDialog');
                if (el) el.remove();
                var overlay = document.getElementById('CybotCookiebotDialogBodyUnderlay');
                if (overlay) overlay.remove();
            """
            )
        except Exception:
            pass

    def _wait_for_page(self, selector=".player-summary-stat-box", max_wait=60):
        for _ in range(max_wait):
            try:
                self.driver.find_element(By.CSS_SELECTOR, selector)
                try:
                    body = self.driver.find_element(By.TAG_NAME, "body").text
                    if "0 maps" in body.lower() or "0 rounds" in body.lower():
                        return "nodata"
                except Exception:
                    pass
                return "ok"
            except Exception:
                pass
            try:
                body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                if "there are no stats" in body or "0 maps" in body:
                    return "nodata"
            except Exception:
                pass
            time.sleep(1)
        return "timeout"

    # ─── Tournament Info Extraction ───────────────────────────────────

    def scrape_tournament_info(self):
        """Extract tournament name, dates, and map pool from the HLTV event page."""
        info_file = self.output_dir / "_tournament_info.json"
        if info_file.exists():
            with open(info_file, encoding="utf-8") as f:
                info = json.load(f)
            self.tournament_name = info["name"]
            self.start_date = info["start_date"]
            self.end_date = info["end_date"]
            self.map_pool = info["map_pool"]
            self.dates = info["match_dates"]
            print(f"  Loaded cached tournament info: {self.tournament_name}")
            return

        self.driver.get(self.event_url)
        time.sleep(6)
        self._dismiss_cookie()

        # Tournament name
        name_el = self.driver.find_elements(By.CSS_SELECTOR, ".event-hub-title")
        self.tournament_name = (
            name_el[0].text.strip() if name_el else f"Event {self.event_id}"
        )

        # Dates (unix timestamps)
        date_spans = []
        for dc in self.driver.find_elements(By.CSS_SELECTOR, ".eventdate"):
            for s in dc.find_elements(By.TAG_NAME, "span"):
                unix = s.get_attribute("data-unix")
                if unix:
                    date_spans.append(int(unix))

        if len(date_spans) >= 2:
            self.start_date = datetime.fromtimestamp(
                min(date_spans) / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")
            self.end_date = datetime.fromtimestamp(
                max(date_spans) / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")
        elif len(date_spans) == 1:
            self.start_date = self.end_date = datetime.fromtimestamp(
                date_spans[0] / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")

        # Map pool
        map_els = self.driver.find_elements(By.CSS_SELECTOR, ".map-pool-map-name")
        self.map_pool = []
        for mp in map_els:
            name = mp.text.strip()
            de_name = MAP_FULLNAME.get(name)
            if de_name:
                self.map_pool.append(de_name)

        # Detect actual match dates from results page
        self.dates = self._detect_match_dates()

        # Cache to file
        self.output_dir.mkdir(parents=True, exist_ok=True)
        info = {
            "name": self.tournament_name,
            "event_id": self.event_id,
            "event_url": self.event_url,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "map_pool": self.map_pool,
            "match_dates": self.dates,
        }
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)

    def _detect_match_dates(self):
        """Scrape the results page to find all dates that have matches."""
        url = (
            f"https://www.hltv.org/results?event={self.event_id}"
            f"&startDate={self.start_date}&endDate={self.end_date}"
        )
        self.driver.get(url)
        time.sleep(5)

        dates_found = set()
        # Each result-con has a link with a date context; use subheaders
        subheaders = self.driver.find_elements(By.CSS_SELECTOR, ".results-subheader")
        for sh in subheaders:
            text = sh.text.strip().lower()
            # Parse "results for january 23rd 2025" etc.
            m = re.search(r"(\w+)\s+(\d+)\w*\s+(\d{4})", text)
            if m:
                month_str, day, year = m.group(1), m.group(2), m.group(3)
                try:
                    dt = datetime.strptime(f"{month_str} {day} {year}", "%B %d %Y")
                    dates_found.add(dt.strftime("%Y-%m-%d"))
                except ValueError:
                    pass

        if not dates_found:
            # Fallback: generate all dates in range
            start = datetime.strptime(self.start_date, "%Y-%m-%d")
            end = datetime.strptime(self.end_date, "%Y-%m-%d")
            current = start
            while current <= end:
                dates_found.add(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)

        return sorted(dates_found)

    # ─── Player List Extraction ──────────────────────────────────────

    def scrape_players_list(self):
        """Extract all player names/IDs from the tournament event page."""
        players_csv = self.output_dir / "players_list.csv"
        if players_csv.exists():
            self._load_players_from_csv()
            return

        self.driver.get(self.event_url)
        time.sleep(5)
        self._dismiss_cookie()

        try:
            btn = self.driver.find_element(By.CSS_SELECTOR, "a.show-lineup-btn")
            btn.click()
            time.sleep(2)
        except Exception:
            pass

        team_boxes = self.driver.find_elements(
            By.CSS_SELECTOR, ".teams-attending .team-box"
        )
        rows = []
        for box in team_boxes:
            try:
                team_name = box.find_element(By.CSS_SELECTOR, ".text").text.strip()
            except Exception:
                continue
            lineup = box.find_elements(
                By.CSS_SELECTOR, '.lineup-box a[href*="/player/"]'
            )
            players = []
            for link in lineup:
                href = link.get_attribute("href") or ""
                match = re.search(r"/player/(\d+)/([^/?]+)", href)
                if match:
                    pname = link.text.strip() or match.group(2)
                    players.append(
                        {
                            "team": team_name,
                            "player_name": pname,
                            "player_id": int(match.group(1)),
                            "player_slug": match.group(2),
                            "player_url": href,
                        }
                    )
            if players:
                rows.extend(players)
                self.players_by_team[team_name] = [
                    {
                        "name": p["player_name"],
                        "id": p["player_id"],
                        "slug": p["player_slug"],
                    }
                    for p in players
                ]

        self.tournament_teams = sorted(self.players_by_team.keys())

        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(players_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "team",
                    "player_name",
                    "player_id",
                    "player_slug",
                    "player_url",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    def _load_players_from_csv(self):
        players_csv = self.output_dir / "players_list.csv"
        with open(players_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                team = row["team"]
                if team not in self.players_by_team:
                    self.players_by_team[team] = []
                self.players_by_team[team].append(
                    {
                        "name": row["player_name"],
                        "id": int(row["player_id"]),
                        "slug": row["player_slug"],
                    }
                )
        self.tournament_teams = sorted(self.players_by_team.keys())

    # ─── Match Schedule Scraping ─────────────────────────────────────

    def scrape_match_schedule(self, match_date):
        """Scrape all matches for a given date from HLTV results page."""
        date_dir = self.output_dir / "matches" / match_date
        matches_file = date_dir / "matches.json"

        if matches_file.exists():
            with open(matches_file, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("matches", [])

        url = f"https://www.hltv.org/results?event={self.event_id}&startDate={match_date}&endDate={match_date}"
        self.driver.get(url)
        time.sleep(4)

        results = self.driver.find_elements(By.CSS_SELECTOR, ".result-con")
        matches = []

        for r in results:
            teams = r.find_elements(By.CSS_SELECTOR, ".team-cell")
            if len(teams) < 2:
                continue
            t1 = teams[0].text.strip()
            t2 = teams[1].text.strip()

            link_el = r.find_element(By.CSS_SELECTOR, "a.a-reset")
            href = link_el.get_attribute("href") or ""
            mid_match = re.search(r"/matches/(\d+)/", href)
            match_id = int(mid_match.group(1)) if mid_match else 0

            map_el = r.find_elements(By.CSS_SELECTOR, ".map-text")
            map_text = map_el[0].text.strip() if map_el else ""

            if map_text in ("bo3", "bo5"):
                bo_format = map_text
                link = r.find_elements(By.CSS_SELECTOR, "a.a-reset")
                if link:
                    self.driver.get(link[0].get_attribute("href"))
                    time.sleep(4)
                    # Only count maps that were actually played (have real scores)
                    map_holders = self.driver.find_elements(
                        By.CSS_SELECTOR, ".mapholder"
                    )
                    maps = []
                    for mh in map_holders:
                        mn_els = mh.find_elements(By.CSS_SELECTOR, ".mapname")
                        score_els = mh.find_elements(
                            By.CSS_SELECTOR, ".results-team-score"
                        )
                        if not mn_els:
                            continue
                        mn = mn_els[0].text.strip()
                        scores = [s.text.strip() for s in score_els]
                        if (
                            mn in MAP_FULLNAME
                            and scores
                            and all(s not in ("-", "") for s in scores)
                        ):
                            maps.append(MAP_FULLNAME[mn])
                    self.driver.back()
                    time.sleep(3)
                    matches.append(
                        {
                            "team1": t1,
                            "team2": t2,
                            "maps": maps,
                            "format": bo_format,
                            "match_id": match_id,
                            "match_url": href,
                        }
                    )
                else:
                    matches.append(
                        {
                            "team1": t1,
                            "team2": t2,
                            "maps": [],
                            "format": bo_format,
                            "match_id": match_id,
                            "match_url": href,
                        }
                    )
            else:
                de_name = MAP_ABBREV.get(map_text)
                if de_name:
                    matches.append(
                        {
                            "team1": t1,
                            "team2": t2,
                            "maps": [de_name],
                            "format": "bo1",
                            "match_id": match_id,
                            "match_url": href,
                        }
                    )

        stats_end = self._date_minus(match_date, 1)
        date_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "match_date": match_date,
            "stats_end_date": stats_end,
            "matches": matches,
        }
        with open(matches_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        teams_playing = set()
        maps_played = set()
        for m in matches:
            teams_playing.update([m["team1"], m["team2"]])
            maps_played.update(m["maps"])

        meta = {
            "date": match_date,
            "stats_end_date": stats_end,
            "total_matches": len(matches),
            "teams_playing": sorted(teams_playing),
            "maps_played": sorted(maps_played),
        }
        with open(date_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        return matches

    # ─── Top Detection ───────────────────────────────────────────────

    def detect_minimum_top(self, team1, team2, map_name, stats_end, window_key):
        """Find minimum ranking filter where both teams appear in HLTV stats."""
        days = WINDOWS[window_key]
        win_start = self._date_minus(stats_end, days - 1)

        for top in TOPS:
            url = (
                f"https://www.hltv.org/stats/teams?csVersion=CS2"
                f"&maps={map_name}&startDate={win_start}&endDate={stats_end}"
                f"&rankingFilter={top}"
            )
            self.driver.get(url)
            time.sleep(3)

            team_set = set()
            for row in self.driver.find_elements(
                By.CSS_SELECTOR, ".stats-table tbody tr"
            ):
                try:
                    name_el = row.find_element(By.CSS_SELECTOR, "td a")
                    team_set.add(name_el.text.strip())
                except Exception:
                    pass

            if team1 in team_set and team2 in team_set:
                return top

        return "Top50"

    def detect_tops_for_date(self, match_date, matches):
        """Detect minimum tops for all matches on a date. Caches to matches.json."""
        matches_file = self.output_dir / "matches" / match_date / "matches.json"

        with open(matches_file, encoding="utf-8") as f:
            data = json.load(f)

        if data["matches"] and "tops" in data["matches"][0]:
            return data["matches"]

        stats_end = self._date_minus(match_date, 1)

        for mi, match in enumerate(matches):
            match["tops"] = {}
            for map_name in match["maps"]:
                match["tops"][map_name] = {}
                for win_key in WINDOWS:
                    top = self.detect_minimum_top(
                        match["team1"], match["team2"], map_name, stats_end, win_key
                    )
                    match["tops"][map_name][win_key] = top
            matches[mi] = match

        data["matches"] = matches
        with open(matches_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return matches

    # ─── Team Stats Scraping ─────────────────────────────────────────

    def _scrape_team_stats_page(self, url, stat_labels, col_offset=2, max_retries=3):
        """Scrape a team stats page and return {team_name: {col: val}}.

        col_offset: column index where stats start in each <tr>.
            Rating page:  Team(0), Maps(1), K-DDiff(2), K/D(3), Rating(4) → offset=4
            FTU page:     Team(0), Maps(1), RW%(2), OpK(3), ...           → offset=2
            Pistol page:  Team(0), Maps(1), Won-Lost(2), Pistol%(3), ...  → offset=3

        Retries up to max_retries times on 500 errors.
        """
        for attempt in range(max_retries):
            self.driver.get(url)
            time.sleep(4 + attempt * 2)

            # Detect 500 / error pages
            body_text = ""
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                if "something went wrong" in body_text or "500" in self.driver.title:
                    if attempt < max_retries - 1:
                        print(f" [500 retry {attempt+1}]", end="", flush=True)
                        time.sleep(5 + attempt * 5)
                        continue
                    else:
                        return {}
            except Exception:
                pass

            result = {}
            rows = self.driver.find_elements(
                By.CSS_SELECTOR, ".stats-table tbody tr"
            )
            for row in rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) <= col_offset:
                    continue
                try:
                    team_name = cols[0].find_element(
                        By.CSS_SELECTOR, "a"
                    ).text.strip()
                except Exception:
                    continue

                team_data = {}
                header_labels = list(stat_labels.values())
                for ci, col_name in enumerate(header_labels):
                    idx = ci + col_offset
                    if idx < len(cols):
                        team_data[col_name] = self._parse_val(cols[idx].text)
                result[team_name] = team_data

            if result:
                return result

            # No rows found — check if page loaded correctly (has HLTV title)
            # vs a real error (empty title = 500/Cloudflare)
            page_title = self.driver.title or ""
            if "hltv" in page_title.lower():
                # Page loaded fine, just no data for this filter → don't retry
                return {}

            # Empty title = possible Cloudflare or error page, retry
            if attempt < max_retries - 1:
                print(f" [retry {attempt+1}]", end="", flush=True)
                time.sleep(5 + attempt * 5)

        return result

    def scrape_team_stats(self, date):
        """Scrape all team stats for a date (rating, FTU, pistol) across all maps/sides/tops/windows."""
        teams_dir = self.output_dir / "teams"

        # Use map pool + global
        all_maps = ["global"] + self.map_pool

        for win_key, days in WINDOWS.items():
            end_date = self._date_minus(date, 1)
            start_date = self._date_minus(end_date, days)

            check_dir = teams_dir / win_key / date
            if check_dir.exists():
                existing = list(check_dir.glob("*.csv"))
                if len(existing) >= len(self.tournament_teams):
                    continue

            sides = ["CT", "T"]
            tops_list = ["Top5", "Top10", "Top20", "Top30", "Top50"]

            team_data = {}

            # Side param differs: /stats/teams uses "ct"/"t",
            # but /stats/teams/ftu and /pistols need "COUNTER_TERRORIST"/"TERRORIST"
            side_short = {"CT": "ct", "T": "t"}
            side_long = {"CT": "COUNTER_TERRORIST", "T": "TERRORIST"}

            for map_name in all_maps:
                map_param = map_name if map_name != "global" else ""
                for side in sides:
                    for top in tops_list:
                        common_params = (
                            f"startDate={start_date}&endDate={end_date}"
                            f"&rankingFilter={top}"
                        )
                        if map_param:
                            common_params += f"&maps={map_param}"

                        # Rating — uses side=ct/t
                        rating_url = (
                            f"https://www.hltv.org/stats/teams"
                            f"?{common_params}&side={side_short[side]}"
                        )
                        # col_offset: index where stats start
                        # Rating:  Team(0) Maps(1) K-DDiff(2) K/D(3) Rating(4) → 4
                        # FTU:     Team(0) Maps(1) RW%(2) OpK(3) ...           → 2
                        # Pistol:  Team(0) Maps(1) Won-Lost(2) Pistol%(3) ...  → 3
                        rating_data = self._scrape_team_stats_page(
                            rating_url, RATING_STAT_LABELS, col_offset=4
                        )

                        # FTU — uses side=COUNTER_TERRORIST/TERRORIST
                        ftu_url = (
                            f"https://www.hltv.org/stats/teams/ftu"
                            f"?{common_params}&side={side_long[side]}"
                        )
                        ftu_data = self._scrape_team_stats_page(
                            ftu_url, FTU_STAT_LABELS, col_offset=2
                        )

                        # Pistol — uses side=COUNTER_TERRORIST/TERRORIST
                        pistol_url = (
                            f"https://www.hltv.org/stats/teams/pistols"
                            f"?{common_params}&side={side_long[side]}"
                        )
                        pistol_data = self._scrape_team_stats_page(
                            pistol_url, PISTOL_STAT_LABELS, col_offset=3
                        )

                        for team in self.tournament_teams:
                            if team not in team_data:
                                team_data[team] = []

                            row = {
                                "map": map_name,
                                "side": side,
                                "top": top.lower(),
                            }
                            r = rating_data.get(team, {})
                            ft = ftu_data.get(team, {})
                            p = pistol_data.get(team, {})

                            row["rating"] = r.get("rating", "N/A")
                            for col in [
                                "rw_pct",
                                "opk_pct",
                                "multik",
                                "pct5v4",
                                "pct4v5",
                                "traded_pct",
                                "adr",
                                "fa",
                            ]:
                                row[col] = ft.get(col, "N/A")
                            for col in [
                                "pistol_win_pct",
                                "round2_conv",
                                "round2_break",
                            ]:
                                row[col] = p.get(col, "N/A")

                            team_data[team].append(row)

            for team, rows in team_data.items():
                df = pd.DataFrame(rows, columns=TEAM_COLUMNS)
                df = self.apply_propagation(df)
                out_dir = teams_dir / win_key / date
                out_dir.mkdir(parents=True, exist_ok=True)
                df.to_csv(out_dir / f"{team}.csv", index=False)

    @staticmethod
    def apply_propagation(df):
        """Downward-only propagation for team stats."""
        stat_cols = [c for c in df.columns if c not in ("map", "side", "top")]
        top_order = ["top5", "top10", "top20", "top30", "top50"]

        for map_name in df["map"].unique():
            for side in df["side"].unique():
                mask_base = (df["map"] == map_name) & (df["side"] == side)

                for i, higher_top in enumerate(top_order):
                    higher_mask = mask_base & (df["top"] == higher_top)
                    if higher_mask.sum() == 0:
                        continue

                    higher_row = df.loc[higher_mask, stat_cols].iloc[0]
                    has_data = any(str(v) not in ("", "N/A", "nan") for v in higher_row)
                    if not has_data:
                        continue

                    for lower_top in top_order[i + 1 :]:
                        lower_mask = mask_base & (df["top"] == lower_top)
                        if lower_mask.sum() == 0:
                            continue

                        lower_row = df.loc[lower_mask, stat_cols].iloc[0]
                        lower_has_data = any(
                            str(v) not in ("", "N/A", "nan") for v in lower_row
                        )
                        if not lower_has_data:
                            for col in stat_cols:
                                df.loc[lower_mask, col] = higher_row[col]

        return df

    # ─── Player Stats Scraping ───────────────────────────────────────

    def _extract_main_stats(self):
        result = {}
        try:
            try:
                box = self.driver.find_element(
                    By.CSS_SELECTOR, ".player-summary-stat-box.compact"
                )
            except Exception:
                box = self.driver.find_element(
                    By.CSS_SELECTOR, ".player-summary-stat-box"
                )
            lines = [l.strip() for l in box.text.split("\n") if l.strip()]
            label_map = {
                "T RATING": ("rating_t", -1),
                "RATING 3.0": ("rating_30", -1),
                "CT RATING": ("rating_ct", -1),
                "ROUND SWING": ("round_swing", -2),
                "DPR": ("dpr", -1),
                "KAST": ("kast", -2),
                "MULTI-KILL": ("multikill", -2),
                "ADR": ("adr", -1),
                "KPR": ("kpr", -1),
            }
            for i, line in enumerate(lines):
                if line in label_map:
                    col, offset = label_map[line]
                    if i + offset >= 0:
                        result[col] = self._parse_val(lines[i + offset])
        except Exception:
            pass
        return result

    def _extract_detailed_side(self, side_key):
        result = {}
        try:
            for row in self.driver.find_elements(
                By.CSS_SELECTOR, f".role-stats-row.stats-side-{side_key}"
            ):
                parts = row.text.strip().split("\n")
                if len(parts) >= 2:
                    col = DETAILED_STAT_MAP.get(parts[0].strip())
                    if col:
                        result[col] = self._parse_val(parts[1].strip())
        except Exception:
            pass
        return result

    def _click_side_and_extract(self, side_attr, side_key):
        try:
            self._dismiss_cookie()
            sels = self.driver.find_elements(
                By.CSS_SELECTOR, f".stats-side-selector[data-side-stats='{side_attr}']"
            )
            if len(sels) >= 2:
                sels[1].click()
            elif len(sels) == 1:
                sels[0].click()
            time.sleep(1.5)

            for sec in self.driver.find_elements(
                By.CSS_SELECTOR, ".role-stats-section"
            ):
                if "active" not in (sec.get_attribute("class") or ""):
                    try:
                        sec.click()
                        time.sleep(0.3)
                    except Exception:
                        pass

            return self._extract_detailed_side(side_key)
        except Exception:
            return {}

    def _extract_general_stats(self):
        result = {}
        try:
            for row in self.driver.find_elements(By.CSS_SELECTOR, ".stats-row"):
                spans = row.find_elements(By.TAG_NAME, "span")
                if len(spans) >= 2:
                    col = GENERAL_STAT_MAP.get(spans[0].text.strip())
                    if col:
                        result[col] = self._parse_val(spans[1].text.strip())
        except Exception:
            pass
        return result

    def _extract_featured_ratings(self):
        result = {}
        try:
            container = self.driver.find_element(
                By.CSS_SELECTOR, ".featured-ratings-container"
            )
            lines = [l.strip() for l in container.text.split("\n") if l.strip()]
            for i, line in enumerate(lines):
                lower = line.lower()
                if "vs top" in lower and "opponents" in lower and i > 0:
                    m = re.search(r"top\s+(\d+)", lower)
                    if m:
                        result[f"rating_vs_top{m.group(1)}"] = self._parse_val(
                            lines[i - 1]
                        )
        except Exception:
            pass
        return result

    def _scrape_player_page(self, url):
        """Scrape a single player stats URL."""
        for attempt in range(3):
            try:
                self.driver.get(url)
                status = self._wait_for_page()
                if status == "nodata":
                    return None, None, None, None, None
                if status == "timeout":
                    if attempt < 2:
                        time.sleep(5)
                        continue
                    return None, None, None, None, None

                time.sleep(0.5)
                self._dismiss_cookie()

                main = self._extract_main_stats()
                ct_det = self._click_side_and_extract("ct", "ct")
                t_det = self._click_side_and_extract("t", "t")
                general = self._extract_general_stats()
                featured = self._extract_featured_ratings()
                return main, ct_det, t_det, general, featured
            except Exception:
                if attempt < 2:
                    time.sleep(5)
        return None, None, None, None, None

    @staticmethod
    def _build_player_row(side, top, main, detailed, general, featured):
        main = main or {}
        detailed = detailed or {}
        general = general or {}
        featured = featured or {}
        row = {"side": side, "top": top}
        for col in MAIN_STATS:
            row[col] = main.get(col, "")
        for col in DETAILED_COLUMNS:
            row[col] = detailed.get(col, "")
        for col in GENERAL_COLUMNS:
            row[col] = general.get(col, "")
        for col in FEATURED_COLUMNS:
            row[col] = featured.get(col, "")
        return row

    def scrape_player_stats(self, player, team, match_date, map_name, top, window_key):
        """Scrape stats for a single player/map/top/window combination."""
        top_lower = top.lower()
        out_dir = self.output_dir / "players" / window_key / match_date / team
        out_file = out_dir / f"{player['name']}_{map_name}_{top_lower}.csv"

        if out_file.exists():
            return "skipped"

        days = WINDOWS[window_key]
        stats_end = self._date_minus(match_date, 1)
        win_start = self._date_minus(match_date, days)

        url = (
            f"https://www.hltv.org/stats/players/{player['id']}/{player['slug']}"
            f"?startDate={win_start}&endDate={stats_end}"
            f"&rankingFilter={top}&maps={map_name}"
        )

        main, ct_det, t_det, general, featured = self._scrape_player_page(url)

        out_dir.mkdir(parents=True, exist_ok=True)

        if main is None and ct_det is None:
            with open(out_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=PLAYER_COLUMNS)
                writer.writeheader()
                for side in ["CT", "T"]:
                    row = {"map": map_name, "side": side, "top": top_lower}
                    for col in PLAYER_COLUMNS[3:]:
                        row[col] = ""
                    writer.writerow(row)
            return "nodata"

        ct_row = self._build_player_row(
            "CT", top_lower, main, ct_det, general or {}, featured
        )
        ct_row["map"] = map_name
        t_row = self._build_player_row(
            "T", top_lower, main, t_det, general or {}, featured
        )
        t_row["map"] = map_name

        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PLAYER_COLUMNS)
            writer.writeheader()
            writer.writerow(ct_row)
            writer.writerow(t_row)

        return "ok"

    # ─── Head-to-Head Stats ────────────────────────────────────────

    def scrape_h2h_stats(self, match_id, match_url, date, team1, team2, maps_played):
        """Scrape head-to-head statistics for a match."""
        safe_t1 = team1.replace(" ", "")
        safe_t2 = team2.replace(" ", "")
        out_dir = self.output_dir / "h2h" / date
        out_file = out_dir / f"{safe_t1}_vs_{safe_t2}.csv"

        if out_file.exists():
            return "skipped"

        if not match_url:
            return "no_url"

        try:
            self.driver.get(match_url)
            time.sleep(4)
            self._dismiss_cookie()
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight / 2);"
            )
            time.sleep(2)

            team1_wins, overtimes, team2_wins = self._extract_h2h_global()
            per_map = self._extract_h2h_per_map()

            rows = [
                {
                    "match_id": match_id,
                    "date": date,
                    "team1": team1,
                    "team2": team2,
                    "team1_h2h_wins": team1_wins,
                    "team2_h2h_wins": team2_wins,
                    "h2h_overtimes": overtimes,
                    "map": "global",
                    "team1_map_wins": "N/A",
                    "team2_map_wins": "N/A",
                    "team1_map_rounds": "N/A",
                    "team2_map_rounds": "N/A",
                }
            ]

            for map_name in maps_played:
                md = per_map.get(map_name, {})
                rows.append(
                    {
                        "match_id": match_id,
                        "date": date,
                        "team1": team1,
                        "team2": team2,
                        "team1_h2h_wins": team1_wins,
                        "team2_h2h_wins": team2_wins,
                        "h2h_overtimes": overtimes,
                        "map": map_name,
                        "team1_map_wins": md.get("team1_wins", 0),
                        "team2_map_wins": md.get("team2_wins", 0),
                        "team1_map_rounds": md.get("team1_rounds", 0),
                        "team2_map_rounds": md.get("team2_rounds", 0),
                    }
                )

            out_dir.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=H2H_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)

            return "ok"

        except Exception:
            return "failed"

    def _extract_h2h_global(self):
        """Extract global H2H wins/overtimes from the match page header."""
        try:
            box = self.driver.find_element(
                By.CSS_SELECTOR, ".standard-box.flexbox.padding"
            )
            bold_divs = box.find_elements(By.CSS_SELECTOR, ".bold")
            if len(bold_divs) >= 3:
                return (
                    int(bold_divs[0].text.strip()),
                    int(bold_divs[1].text.strip()),
                    int(bold_divs[2].text.strip()),
                )
        except Exception:
            pass
        return 0, 0, 0

    def _extract_h2h_per_map(self):
        """Extract per-map H2H stats from the match listing table."""
        result = {}
        try:
            listing = self.driver.find_element(By.CSS_SELECTOR, ".head-to-head-listing")
            rows = listing.find_elements(By.CSS_SELECTOR, "tr.row")

            for row in rows:
                try:
                    map_el = row.find_element(By.CSS_SELECTOR, ".dynamic-map-name-full")
                    map_name = map_el.text.strip()
                    de_name = MAP_FULLNAME.get(map_name, map_name)

                    result_el = row.find_element(By.CSS_SELECTOR, "td.result")
                    spans = result_el.find_elements(By.TAG_NAME, "span")
                    if len(spans) < 2:
                        continue
                    t1_score = int(spans[0].text.strip())
                    t2_score = int(spans[1].text.strip())

                    team1_td = row.find_element(By.CSS_SELECTOR, "td.team1")
                    team1_won = "winner" in (team1_td.get_attribute("class") or "")

                    if de_name not in result:
                        result[de_name] = {
                            "team1_wins": 0,
                            "team2_wins": 0,
                            "team1_rounds": 0,
                            "team2_rounds": 0,
                        }

                    result[de_name]["team1_rounds"] += t1_score
                    result[de_name]["team2_rounds"] += t2_score
                    if team1_won:
                        result[de_name]["team1_wins"] += 1
                    else:
                        result[de_name]["team2_wins"] += 1
                except Exception:
                    continue
        except Exception:
            pass
        return result

    # ─── Demo Download ────────────────────────────────────────────────

    def download_demos(self, all_matches):
        """Download and extract demo files for all matches.

        Uses CDP Browser.setDownloadBehavior + JS navigation to trigger
        downloads inside the browser (bypasses Cloudflare).
        """
        if not self.demo_dir:
            print("  [SKIP] No demo_dir configured")
            return

        temp_dir = self.output_dir / "_temp_downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)

        demo_count = 0
        demo_skipped = 0
        demo_failed = 0

        # Set download path via CDP (both levels for compat)
        try:
            self.driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": str(temp_dir),
                "eventsEnabled": True,
            })
        except Exception:
            pass
        try:
            self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": str(temp_dir),
            })
        except Exception:
            pass

        for date in self.dates:
            matches = all_matches.get(date, [])
            for match in matches:
                t1 = match["team1"]
                t2 = match["team2"]
                maps = match.get("maps", [])
                match_url = match.get("match_url", "")
                slug1 = self._slugify(t1)
                slug2 = self._slugify(t2)

                date_dir = self.demo_dir / date
                expected_pattern = f"{date}-{slug1}-vs-{slug2}"

                # Check if already downloaded
                if date_dir.exists():
                    existing = list(date_dir.glob(f"{expected_pattern}*.dem"))
                    if len(existing) >= len(maps) and len(existing) > 0:
                        demo_skipped += len(existing)
                        continue

                if not match_url:
                    continue

                # Navigate to match page to find demo link
                self.driver.get(match_url)
                time.sleep(6)
                for _ in range(10):
                    if (
                        "vs" in self.driver.title.lower()
                        or "hltv" in self.driver.title.lower()
                    ):
                        break
                    time.sleep(2)

                # Find demo download URL
                demo_url = None
                for link in self.driver.find_elements(By.TAG_NAME, "a"):
                    href = link.get_attribute("href") or ""
                    if "/download/demo/" in href:
                        demo_url = href
                        break

                if not demo_url:
                    print(f"    {t1} vs {t2}: No demo link")
                    demo_failed += 1
                    continue

                # Clear temp dir
                for f in temp_dir.iterdir():
                    if f.is_file():
                        try:
                            f.unlink()
                        except Exception:
                            pass

                # Trigger download via JS navigation (stays in Cloudflare session)
                print(f"    {t1} vs {t2}: downloading...", end="", flush=True)
                self.driver.execute_script(f"window.location.href = '{demo_url}'")

                # Wait for download to complete
                downloaded = None
                start_time = time.time()
                while time.time() - start_time < 600:
                    time.sleep(3)
                    elapsed = int(time.time() - start_time)

                    for f in temp_dir.iterdir():
                        if not f.is_file():
                            continue
                        if f.name.endswith(".crdownload"):
                            size_mb = f.stat().st_size / (1024 * 1024)
                            print(
                                f"\r    {t1} vs {t2}: downloading... {size_mb:.0f} MB ({elapsed}s)   ",
                                end="", flush=True,
                            )
                        elif f.suffix in (".rar", ".zip", ".gz") and f.stat().st_size > 1000:
                            downloaded = f
                            break
                    if downloaded:
                        size_mb = downloaded.stat().st_size / (1024 * 1024)
                        print(
                            f"\r    {t1} vs {t2}: done ({size_mb:.0f} MB, {elapsed}s)                    "
                        )
                        break

                if not downloaded:
                    print(f" TIMEOUT")
                    demo_failed += 1
                    continue

                # Extract archive with 7-Zip
                date_dir.mkdir(parents=True, exist_ok=True)
                extract_dir = temp_dir / "extracted"
                extract_dir.mkdir(exist_ok=True)

                try:
                    result = subprocess.run(
                        [SEVENZ, "x", str(downloaded), f"-o{extract_dir}", "-y"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(result.stderr)

                    for dem_file in extract_dir.rglob("*.dem"):
                        map_name = "unknown"
                        for m in DEMO_MAP_NAMES:
                            if m in dem_file.name.lower():
                                map_name = m
                                break
                        final_name = f"{date}-{slug1}-vs-{slug2}-{map_name}.dem"
                        dest = date_dir / final_name
                        shutil.move(str(dem_file), str(dest))
                        demo_count += 1
                        print(
                            f"      -> {final_name} ({dest.stat().st_size/(1024*1024):.0f} MB)"
                        )

                except Exception as e:
                    print(f"    [ERROR] Extraction failed: {e}")
                    demo_failed += 1

                # Clean up temp
                for f in temp_dir.rglob("*"):
                    if f.is_file():
                        try:
                            f.unlink()
                        except Exception:
                            pass
                if extract_dir.exists():
                    shutil.rmtree(extract_dir, ignore_errors=True)

        # Clean up temp dir
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        print(
            f"  Demos downloaded: {demo_count}, skipped: {demo_skipped}, failed: {demo_failed}"
        )

    # ─── Metadata ────────────────────────────────────────────────────

    def save_metadata(self):
        """Save tournament metadata."""
        meta = {
            "tournament": {
                "name": self.tournament_name,
                "hltv_event_id": self.event_id,
                "event_url": self.event_url,
            },
            "dates": {
                "start": self.start_date,
                "end": self.end_date,
                "match_dates": self.dates,
            },
            "map_pool": self.map_pool,
            "maps_scraped": ["global"] + self.map_pool,
            "teams": {
                "total_scraped": len(self.tournament_teams),
                "list": self.tournament_teams,
                "sides": ["CT", "T"],
            },
            "stats": {
                "team_columns": TEAM_COLUMNS,
                "player_columns": PLAYER_COLUMNS,
                "h2h_columns": H2H_COLUMNS,
                "windows": list(WINDOWS.keys()),
                "rankings": ["top5", "top10", "top20", "top30", "top50"],
            },
            "structure": {
                "teams": "teams/{window}/{date}/{team}.csv",
                "players": "players/{window}/{date}/{team}/{player}_{map}_{top}.csv",
                "h2h": "h2h/{date}/{team1}_vs_{team2}.csv",
                "demos": (
                    "demos/{date}/{date}-{team1}-vs-{team2}-{map}.dem"
                    if self.demo_dir
                    else None
                ),
            },
            "players": {
                "total": sum(len(v) for v in self.players_by_team.values()),
                "by_team": self.players_by_team,
            },
        }
        with open(self.output_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    # ─── Main Pipeline ───────────────────────────────────────────────

    def scrape_tournament(self):
        """Full tournament scraping pipeline."""
        global_start = time.time()

        self._init_driver()

        total_urls = 0
        total_skipped = 0
        total_nodata = 0

        try:
            # Phase 0: Extract tournament info (name, dates, map pool)
            print("Extracting tournament info...")
            self.scrape_tournament_info()
            print(f"  Name: {self.tournament_name}")
            print(f"  Dates: {self.start_date} to {self.end_date}")
            print(f"  Match days: {', '.join(self.dates)}")
            print(f"  Map pool: {', '.join(self.map_pool)}")

            # Extract players list
            print("\nExtracting players list...")
            self.scrape_players_list()
            print(
                f"  {len(self.tournament_teams)} teams, "
                f"{sum(len(v) for v in self.players_by_team.values())} players"
            )

            # Scrape team stats for all dates
            print("\nScraping team stats...")
            for date in self.dates:
                print(f"  {date}...", end=" ", flush=True)
                self.scrape_team_stats(date)
                print("done")

            # Phase 1: Scrape match schedules
            print("\nScraping match schedules...")
            all_matches = {}
            for date in self.dates:
                matches = self.scrape_match_schedule(date)
                all_matches[date] = matches
                print(f"  {date}: {len(matches)} matches")

            # Phase 2: Detect minimum tops
            print("\nDetecting minimum tops...")
            for date in self.dates:
                matches = all_matches.get(date, [])
                if not matches:
                    continue
                matches = self.detect_tops_for_date(date, matches)
                all_matches[date] = matches
                print(f"  {date}: tops detected for {len(matches)} matches")

            # Phase 3: Scrape player stats (optimized)
            print("\nScraping player stats...")

            for date in self.dates:
                matches = all_matches.get(date, [])
                if not matches:
                    continue

                for match in matches:
                    tops_map = match.get("tops", {})
                    for map_name in match["maps"]:
                        for win_key in WINDOWS:
                            top = tops_map.get(map_name, {}).get(win_key, "Top50")

                            for team in [match["team1"], match["team2"]]:
                                players = self.players_by_team.get(team, [])
                                for player in players:
                                    result = self.scrape_player_stats(
                                        player, team, date, map_name, top, win_key
                                    )
                                    if result == "skipped":
                                        total_skipped += 1
                                    elif result == "nodata":
                                        total_nodata += 1
                                        total_urls += 1
                                        time.sleep(2)
                                    else:
                                        total_urls += 1
                                        time.sleep(2)

                elapsed = (time.time() - global_start) / 60
                print(
                    f"  {date}: {total_urls} scraped, {total_skipped} skipped, {elapsed:.0f} min elapsed"
                )

            # Phase 4: Scrape H2H stats
            print("\nScraping head-to-head stats...")
            h2h_count = 0
            for date in self.dates:
                matches = all_matches.get(date, [])
                for match in matches:
                    result = self.scrape_h2h_stats(
                        match.get("match_id", 0),
                        match.get("match_url", ""),
                        date,
                        match["team1"],
                        match["team2"],
                        match.get("maps", []),
                    )
                    if result == "ok":
                        h2h_count += 1
                        time.sleep(2)
                    elif result != "skipped":
                        time.sleep(2)
                if matches:
                    print(f"  {date}: {len(matches)} matches processed")
            print(f"  H2H files created: {h2h_count}")

            # Phase 5: Download demos
            if self.demo_dir:
                print("\nDownloading demos...")
                self.download_demos(all_matches)

            # Save metadata
            self.save_metadata()

        except KeyboardInterrupt:
            print("\n\nInterrupted by user.")
        except Exception as e:
            print(f"\nError: {e}")
            import traceback

            traceback.print_exc()
        finally:
            try:
                self.driver.quit()
            except Exception:
                pass

        elapsed = (time.time() - global_start) / 60
        print(f"\nComplete in {elapsed:.1f} min")
        print(f"  URLs scraped: {total_urls}")
        print(f"  Skipped (cached): {total_skipped}")
        print(f"  No-data pages: {total_nodata}")


if __name__ == "__main__":
    import sys

    from config import TOURNAMENTS, STATS_DIR, RAW_DIR

    # Default or CLI argument
    tournament_key = sys.argv[1] if len(sys.argv) > 1 else "blast-open-lisbon-2025"

    if tournament_key not in TOURNAMENTS:
        print(f"Unknown tournament: {tournament_key}")
        print(f"Available: {', '.join(TOURNAMENTS.keys())}")
        sys.exit(1)

    event_url = TOURNAMENTS[tournament_key]
    output_dir = STATS_DIR / tournament_key
    demo_dir = RAW_DIR / tournament_key

    print(f"Tournament : {tournament_key}")
    print(f"URL        : {event_url}")
    print(f"Stats dir  : {output_dir}")
    print(f"Demo dir   : {demo_dir}")
    print()

    scraper = TournamentScraper(
        event_url=event_url,
        output_dir=str(output_dir),
        demo_dir=str(demo_dir),
    )
    scraper.scrape_tournament()
