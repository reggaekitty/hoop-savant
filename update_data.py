import json
import os
import time
from datetime import datetime, timezone
from nba_api.stats.endpoints import (
    leaguedashplayerstats,
    leaguedashplayerptshot,
    leaguedashptdefend,
    leaguehustlestatsplayer,
    playerdashptreb
)

SEASONS = [
    "2026-27", "2025-26", "2024-25", "2023-24", "2022-23",
    "2021-22", "2020-21", "2019-20", "2018-19", "2017-18", "2016-17"
]

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


def safe_call(fn, **kwargs):
    for attempt in range(3):
        try:
            res = fn(timeout=45, **kwargs)
            return res.get_normalized_dict()
        except Exception as e:
            print(f"  [Attempt {attempt + 1}/3] {fn.__name__} failed: {e}")
            time.sleep(2 * (attempt + 1))
    return {}


def build_shooting_season(season):
    print(f"[{season}] Fetching Shooting data...")
    base = safe_call(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        season_type_all_star="Regular Season",
        per_mode_detailed="Totals"
    ).get("LeagueDashPlayerStats", [])
    time.sleep(0.8)

    bio = safe_call(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Base"
    ).get("LeagueDashPlayerStats", [])
    pos_map = {}
    for r in bio:
        # fallback position mapping if available
        pos_map[r["PLAYER_ID"]] = ""

    ranges = {
        "Overall": None,
        "Catch and Shoot": "Catch and Shoot",
        "Pullups": "Pullups",
        "Less Than 10 ft": "Less Than 10 ft"
    }
    range_data = {}
    for label, general_range in ranges.items():
        kwargs = {
            "season": season,
            "season_type_all_star": "Regular Season",
            "per_mode_simple": "Totals"
        }
        if general_range:
            kwargs["general_range_nullable"] = general_range
        rows = safe_call(leaguedashplayerptshot.LeagueDashPlayerPtShot, **kwargs).get("LeagueDashPlayerPtShot", [])
        range_data[label] = {r["PLAYER_ID"]: r for r in rows}
        time.sleep(0.8)

    players = []
    for r in base:
        pid = r["PLAYER_ID"]
        gp = r.get("GP", 0)
        if gp == 0:
            continue
        r_dict = {}
        for label, pmap in range_data.items():
            sr = pmap.get(pid)
            if sr:
                r_dict[label] = [
                    sr.get("FGM", 0),
                    sr.get("FGA", 0),
                    sr.get("FG2M", 0),
                    sr.get("FG2A", 0),
                    sr.get("FG3M", 0),
                    sr.get("FG3A", 0),
                    round(sr.get("FGA_FREQUENCY", 0), 4),
                    round(sr.get("FG2A_FREQUENCY", 0), 4),
                    round(sr.get("FG3A_FREQUENCY", 0), 4)
                ]
        # 6 shooting zones approximation from base or shot dashboard if stored
        z = [[0, 0] for _ in range(6)]
        players.append({
            "id": pid,
            "n": r.get("PLAYER_NAME"),
            "t": r.get("TEAM_ABBREVIATION"),
            "pos": pos_map.get(pid, ""),
            "age": int(r.get("AGE") or 0),
            "gp": gp,
            "g": gp,
            "r": r_dict,
            "z": z
        })
    return players


def build_defense_season(season):
    print(f"[{season}] Fetching Defense data...")
    adv = safe_call(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Defense",
        per_mode_detailed="Totals"
    ).get("LeagueDashPlayerStats", [])
    time.sleep(0.8)

    hustle = safe_call(
        leaguehustlestatsplayer.LeagueHustleStatsPlayer,
        season=season,
        season_type_all_star="Regular Season",
        per_mode_time="Totals"
    ).get("HustleStatsPlayer", [])
    hustle_map = {r["PLAYER_ID"]: r for r in hustle}
    time.sleep(0.8)

    def_ranges = ["Overall", "2 Pointers", "3 Pointers", "Less Than 6Ft", "Greater Than 15Ft"]
    def_map = {}
    for cat in def_ranges:
        rows = safe_call(
            leaguedashptdefend.LeagueDashPtDefend,
            season=season,
            season_type_all_star="Regular Season",
            per_mode_simple="Totals",
            defense_category=cat
        ).get("LeagueDashPTDefend", [])
        def_map[cat] = {r["CLOSE_DEF_PERSON_ID"]: r for r in rows}
        time.sleep(0.8)

    players = []
    for r in adv:
        pid = r["PLAYER_ID"]
        gp = r.get("GP", 0)
        if gp == 0:
            continue
        h = hustle_map.get(pid, {})
        # d array: [DEF_RATING, DREB, DREB_PCT, STL, STL_PCT, BLK, BLK_PCT, DEF_WS, CONTESTED_SHOTS, DEFLECTIONS, CHARGES_DRAWN]
        d_arr = [
            r.get("DEF_RATING"),
            r.get("DREB", 0),
            r.get("DREB_PCT"),
            r.get("STL", 0),
            r.get("PCT_STL"),
            r.get("BLK", 0),
            r.get("PCT_BLK"),
            r.get("DEF_WS"),
            h.get("CONTESTED_SHOTS", 0),
            h.get("DEFLECTIONS", 0),
            h.get("CHARGES_DRAWN", 0)
        ]
        r_dict = {}
        for cat, cmap in def_map.items():
            dr = cmap.get(pid)
            if dr:
                r_dict[cat] = [
                    dr.get("D_FGM", 0),
                    dr.get("D_FGA", 0),
                    dr.get("D_FG_PCT"),
                    dr.get("NORMAL_FG_PCT"),
                    dr.get("PCT_PLUSMINUS")
                ]
        players.append({
            "id": pid,
            "n": r.get("PLAYER_NAME"),
            "t": r.get("TEAM_ABBREVIATION"),
            "pos": "",
            "age": int(r.get("AGE") or 0),
            "gp": gp,
            "m": r.get("MIN", 0),
            "d": d_arr,
            "r": r_dict
        })

    out_path = os.path.join(DATA_DIR, f"defense-{season}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(players, f, separators=(",", ":"))
    print(f"  Saved {len(players)} players -> {out_path}")


def build_rebounding_season(season):
    print(f"[{season}] Fetching Offensive & Defensive Rebounding data...")
    # 1. Base totals (OREB, DREB, REB, MIN, GP)
    base = safe_call(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Base",
        per_mode_detailed="Totals"
    ).get("LeagueDashPlayerStats", [])
    time.sleep(0.8)

    # 2. Advanced rebounding percentages (OREB_PCT, DREB_PCT, REB_PCT)
    adv = safe_call(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Advanced",
        per_mode_detailed="Totals"
    ).get("LeagueDashPlayerStats", [])
    adv_map = {r["PLAYER_ID"]: r for r in adv}
    time.sleep(0.8)

    # 3. Hustle box-outs (BOX_OUTS, OFF_BOXOUTS, DEF_BOXOUTS, BOX_OUT_PLAYER_TEAM_REBS)
    hustle = safe_call(
        leaguehustlestatsplayer.LeagueHustleStatsPlayer,
        season=season,
        season_type_all_star="Regular Season",
        per_mode_time="Totals"
    ).get("HustleStatsPlayer", [])
    hustle_map = {r["PLAYER_ID"]: r for r in hustle}
    time.sleep(0.8)

    players = []
    for r in base:
        pid = r["PLAYER_ID"]
        gp = r.get("GP", 0)
        if gp == 0:
            continue
        a = adv_map.get(pid, {})
        h = hustle_map.get(pid, {})

        oreb = r.get("OREB", 0)
        dreb = r.get("DREB", 0)
        reb = r.get("REB", 0)
        oreb_pct = a.get("OREB_PCT")
        dreb_pct = a.get("DREB_PCT")
        reb_pct = a.get("REB_PCT")

        box_outs = h.get("BOX_OUTS", 0)
        off_boxouts = h.get("OFF_BOXOUTS", 0)
        def_boxouts = h.get("DEF_BOXOUTS", 0)
        box_out_rebs = h.get("BOX_OUT_PLAYER_REBS", 0)
        loose_balls = h.get("LOOSE_BALLS_RECOVERED", 0)

        # rb array:
        # [0: OREB, 1: OREB_PCT, 2: DREB, 3: DREB_PCT, 4: REB, 5: REB_PCT,
        #  6: BOX_OUTS, 7: OFF_BOXOUTS, 8: DEF_BOXOUTS, 9: BOX_OUT_PLAYER_REBS, 10: LOOSE_BALLS]
        rb_arr = [
            oreb, oreb_pct, dreb, dreb_pct, reb, reb_pct,
            box_outs, off_boxouts, def_boxouts, box_out_rebs, loose_balls
        ]

        # Breakdown by Rebound Type for the range selector:
        # "Overall", "Offensive", "Defensive"
        # Format per range: [REBS, REB_PCT, BOX_OUTS, BOX_OUT_REBS]
        r_dict = {
            "Overall": [reb, reb_pct, box_outs, box_out_rebs],
            "Offensive": [oreb, oreb_pct, off_boxouts, None],
            "Defensive": [dreb, dreb_pct, def_boxouts, None]
        }

        players.append({
            "id": pid,
            "n": r.get("PLAYER_NAME"),
            "t": r.get("TEAM_ABBREVIATION"),
            "pos": "",
            "age": int(r.get("AGE") or 0),
            "gp": gp,
            "m": r.get("MIN", 0),
            "rb": rb_arr,
            "r": r_dict
        })

    out_path = os.path.join(DATA_DIR, f"rebounding-{season}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(players, f, separators=(",", ":"))
    print(f"  Saved {len(players)} players -> {out_path}")


if __name__ == "__main__":
    valid_seasons = []
    for season in SEASONS:
        try:
            build_rebounding_season(season)
            build_defense_season(season)
            valid_seasons.append(season)
        except Exception as err:
            print(f"Skipping {season}: {err}")

    meta_path = os.path.join(DATA_DIR, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["updated"] = datetime.now(timezone.utc).isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
