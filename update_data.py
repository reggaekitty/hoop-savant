import json
import os
import time
import requests
from datetime import datetime

# Configuration for NBA Stats API
SEASONS = [
    "2025-26", "2024-25", "2023-24", "2022-23", "2021-22",
    "2020-21", "2019-20", "2018-19", "2017-18", "2016-17", "2015-16"
]

HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Connection": "keep-alive",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com"
}

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_nba_endpoint(endpoint, params):
    url = f"https://stats.nba.com/stats/{endpoint}"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            result_set = data["resultSets"][0]
            headers = result_set["headers"]
            rows = result_set["rowSet"]
            return [dict(zip(headers, row)) for row in rows]
        except Exception as e:
            print(f"  [Attempt {attempt + 1}/3] Error fetching {endpoint}: {e}")
            time.sleep(2 * (attempt + 1))
    return []


def compute_percentiles(players, keys):
    for key in keys:
        valid = [p[key] for p in players if p.get(key) is not None]
        if not valid:
            for p in players:
                p[f"{key}_PCT"] = None
            continue
        valid_sorted = sorted(valid)
        n = len(valid_sorted)
        # For opponent FG% and Defensive Rating, lower is better
        invert = key in {"DEF_RATING", "D_FG_PCT", "PCT_PLUSMINUS", "LT_06_FG_PCT", "GT_15_FG_PCT"}
        for p in players:
            val = p.get(key)
            if val is None:
                p[f"{key}_PCT"] = None
                continue
            rank = sum(1 for v in valid_sorted if v <= val)
            pct = round((rank / n) * 100)
            if invert:
                pct = 100 - pct
            p[f"{key}_PCT"] = max(1, min(99, pct))


def build_season_defense(season):
    print(f"Fetching defensive & hustle metrics for {season}...")

    # 1. Advanced Defensive Metrics (DEF_RATING, DREB_PCT, STL, BLK, DEF_WS)
    adv_params = {
        "MeasureType": "Defense",
        "PerMode": "PerGame",
        "PlusMinus": "N",
        "PaceAdjust": "N",
        "Rank": "N",
        "LeagueID": "00",
        "Season": season,
        "SeasonType": "Regular Season",
        "Outcome": "",
        "Location": "",
        "Month": "0",
        "SeasonSegment": "",
        "DateFrom": "",
        "DateTo": "",
        "OpponentTeamID": "0",
        "VsConference": "",
        "VsDivision": "",
        "GameSegment": "",
        "Period": "0",
        "LastNGames": "0",
        "GameScope": "",
        "PlayerExperience": "",
        "PlayerPosition": "",
        "StarterBench": "",
        "DraftYear": "",
        "DraftPick": "",
        "College": "",
        "Country": "",
        "Height": "",
        "Weight": ""
    }
    adv_rows = fetch_nba_endpoint("leaguedashplayerstats", adv_params)
    time.sleep(1.0)

    # 2. Overall Defensive Tracking (Opponent FG% & Diff%)
    overall_params = {
        "DefenseCategory": "Overall",
        "LeagueID": "00",
        "PerMode": "PerGame",
        "Season": season,
        "SeasonType": "Regular Season",
        "PORound": "0",
        "Outcome": "",
        "Location": "",
        "Month": "0",
        "SeasonSegment": "",
        "DateFrom": "",
        "DateTo": "",
        "OpponentTeamID": "0",
        "VsConference": "",
        "VsDivision": "",
        "TeamID": "0",
        "Conference": "",
        "Division": "",
        "GameSegment": "",
        "Period": "0",
        "LastNGames": "0",
        "PlayerExperience": "",
        "PlayerPosition": "",
        "StarterBench": ""
    }
    overall_rows = fetch_nba_endpoint("leaguedashptdefend", overall_params)
    time.sleep(1.0)

    # 3. Rim Protection (< 6ft)
    rim_params = dict(overall_params, DefenseCategory="Less Than 6Ft")
    rim_rows = fetch_nba_endpoint("leaguedashptdefend", rim_params)
    time.sleep(1.0)

    # 4. Perimeter Defense (> 15ft)
    perim_params = dict(overall_params, DefenseCategory="Greater Than 15Ft")
    perim_rows = fetch_nba_endpoint("leaguedashptdefend", perim_params)
    time.sleep(1.0)

    # 5. Player Hustle Stats (Deflections, Loose Balls, Contested Shots, Charges)
    hustle_params = {
        "PerMode": "PerGame",
        "Season": season,
        "SeasonType": "Regular Season",
        "LeagueID": "00"
    }
    hustle_rows = fetch_nba_endpoint("leaguehustlestatsplayer", hustle_params)
    time.sleep(1.0)

    players_map = {}

    for r in adv_rows:
        pid = r["PLAYER_ID"]
        gp = r.get("GP", 0)
        mins = r.get("MIN", 0)
        if gp < 10 or mins < 10:
            continue
        players_map[pid] = {
            "PLAYER_ID": pid,
            "PLAYER_NAME": r.get("PLAYER_NAME"),
            "TEAM_ABBREVIATION": r.get("TEAM_ABBREVIATION"),
            "AGE": r.get("AGE"),
            "GP": gp,
            "MIN": round(mins, 1),
            "DEF_RATING": r.get("DEF_RATING"),
            "DREB": r.get("DREB"),
            "DREB_PCT": round((r.get("DREB_PCT") or 0) * 100, 1),
            "STL": r.get("STL"),
            "BLK": r.get("BLK"),
            "DEF_WS": r.get("DEF_WS"),
            "D_FG_PCT": None,
            "NORMAL_FG_PCT": None,
            "PCT_PLUSMINUS": None,
            "D_FGA": None,
            "LT_06_FG_PCT": None,
            "LT_06_PLUSMINUS": None,
            "GT_15_FG_PCT": None,
            "GT_15_PLUSMINUS": None,
            "CONTESTED_SHOTS": None,
            "CONTESTED_SHOTS_2PT": None,
            "CONTESTED_SHOTS_3PT": None,
            "DEFLECTIONS": None,
            "CHARGES_DRAWN": None,
            "LOOSE_BALLS_RECOVERED": None,
            "BOX_OUTS": None
        }

    for r in overall_rows:
        pid = r.get("CLOSE_DEF_PERSON_ID")
        if pid in players_map:
            players_map[pid]["D_FG_PCT"] = round((r.get("D_FG_PCT") or 0) * 100, 1)
            players_map[pid]["NORMAL_FG_PCT"] = round((r.get("NORMAL_FG_PCT") or 0) * 100, 1)
            players_map[pid]["PCT_PLUSMINUS"] = round((r.get("PCT_PLUSMINUS") or 0) * 100, 1)
            players_map[pid]["D_FGA"] = r.get("D_FGA")

    for r in rim_rows:
        pid = r.get("CLOSE_DEF_PERSON_ID")
        if pid in players_map:
            players_map[pid]["LT_06_FG_PCT"] = round((r.get("LT_06_FG_PCT") or 0) * 100, 1)
            players_map[pid]["LT_06_PLUSMINUS"] = round((r.get("LT_06_PLUSMINUS") or 0) * 100, 1)

    for r in perim_rows:
        pid = r.get("CLOSE_DEF_PERSON_ID")
        if pid in players_map:
            players_map[pid]["GT_15_FG_PCT"] = round((r.get("GT_15_FG_PCT") or 0) * 100, 1)
            players_map[pid]["GT_15_PLUSMINUS"] = round((r.get("GT_15_PLUSMINUS") or 0) * 100, 1)

    for r in hustle_rows:
        pid = r.get("PLAYER_ID")
        if pid in players_map:
            players_map[pid]["CONTESTED_SHOTS"] = r.get("CONTESTED_SHOTS")
            players_map[pid]["CONTESTED_SHOTS_2PT"] = r.get("CONTESTED_SHOTS_2PT")
            players_map[pid]["CONTESTED_SHOTS_3PT"] = r.get("CONTESTED_SHOTS_3PT")
            players_map[pid]["DEFLECTIONS"] = r.get("DEFLECTIONS")
            players_map[pid]["CHARGES_DRAWN"] = r.get("CHARGES_DRAWN")
            players_map[pid]["LOOSE_BALLS_RECOVERED"] = r.get("LOOSE_BALLS_RECOVERED")
            players_map[pid]["BOX_OUTS"] = r.get("BOX_OUTS")

    player_list = list(players_map.values())
    percentile_keys = [
        "DEF_RATING", "D_FG_PCT", "PCT_PLUSMINUS", "LT_06_FG_PCT", "GT_15_FG_PCT",
        "STL", "BLK", "DREB_PCT", "DEF_WS",
        "CONTESTED_SHOTS", "DEFLECTIONS", "LOOSE_BALLS_RECOVERED", "CHARGES_DRAWN", "BOX_OUTS"
    ]
    compute_percentiles(player_list, percentile_keys)

    # Sort default by Defensive Win Shares descending
    player_list.sort(key=lambda x: (x.get("DEF_WS") or 0), reverse=True)

    output_path = os.path.join(OUTPUT_DIR, f"defense-{season}.json")
    payload = {
        "season": season,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(player_list),
        "players": player_list
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {len(player_list)} players to {output_path}")


if __name__ == "__main__":
    for s in SEASONS:
        build_season_defense(s)
