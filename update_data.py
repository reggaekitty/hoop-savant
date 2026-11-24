import json
import os
import time
from datetime import datetime, timezone
from nba_api.stats.static import teams as nba_teams
from nba_api.stats.endpoints import (
    leaguedashplayerstats,
    leaguedashplayerptshot,
    leaguedashptdefend,
    leaguehustlestatsplayer,
    teamplayeronoffsummary
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
    base = safe_call(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Base",
        per_mode_detailed="Totals"
    ).get("LeagueDashPlayerStats", [])
    time.sleep(0.8)

    adv = safe_call(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Advanced",
        per_mode_detailed="Totals"
    ).get("LeagueDashPlayerStats", [])
    adv_map = {r["PLAYER_ID"]: r for r in adv}
    time.sleep(0.8)

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

        rb_arr = [
            oreb, oreb_pct, dreb, dreb_pct, reb, reb_pct,
            box_outs, off_boxouts, def_boxouts, box_out_rebs, loose_balls
        ]

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


def build_on_off_season(season):
    print(f"[{season}] Fetching Team Player On/Off Advanced Ratings...")
    # Base player info for age, games played, and minutes
    base = safe_call(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Base",
        per_mode_detailed="Totals"
    ).get("LeagueDashPlayerStats", [])
    base_map = {r["PLAYER_ID"]: r for r in base}
    time.sleep(0.8)

    all_teams = nba_teams.get_teams()
    # Aggregate across teams (handles mid-season trades by weighting by on-court minutes)
    agg = {}

    for tm in all_teams:
        tid = tm["id"]
        abbr = tm["abbreviation"]
        res = safe_call(
            teamplayeronoffsummary.TeamPlayerOnOffSummary,
            team_id=tid,
            season=season,
            season_type_all_star="Regular Season",
            measure_type_detailed_defense="Advanced",
            per_mode_detailed="Totals"
        )
        on_rows = res.get("PlayersOnCourtTeamPlayerOnOffSummary", [])
        off_rows = res.get("PlayersOffCourtTeamPlayerOnOffSummary", [])
        off_by_pid = {r["VS_PLAYER_ID"]: r for r in off_rows}

        for on_r in on_rows:
            pid = on_r.get("VS_PLAYER_ID")
            off_r = off_by_pid.get(pid)
            if not pid or not off_r:
                continue

            on_min = float(on_r.get("MIN") or 0)
            off_min = float(off_r.get("MIN") or 0)
            if on_min <= 0:
                continue

            on_ortg = float(on_r.get("OFF_RATING") or 0)
            on_drtg = float(on_r.get("DEF_RATING") or 0)
            on_nrtg = float(on_r.get("NET_RATING") or 0)
            on_pace = float(on_r.get("PACE") or 0)

            off_ortg = float(off_r.get("OFF_RATING") or 0)
            off_drtg = float(off_r.get("DEF_RATING") or 0)
            off_nrtg = float(off_r.get("NET_RATING") or 0)

            if pid not in agg:
                b = base_map.get(pid, {})
                # Format player name from "Last, First" if needed
                raw_name = on_r.get("VS_PLAYER_NAME", "")
                if ", " in raw_name:
                    parts = raw_name.split(", ", 1)
                    clean_name = f"{parts[1]} {parts[0]}"
                else:
                    clean_name = raw_name

                agg[pid] = {
                    "id": pid,
                    "n": b.get("PLAYER_NAME") or clean_name,
                    "t": b.get("TEAM_ABBREVIATION") or abbr,
                    "pos": "",
                    "age": int(b.get("AGE") or 0),
                    "gp": int(b.get("GP") or on_r.get("GP") or 0),
                    "on_min": 0.0,
                    "off_min": 0.0,
                    "w_on_ortg": 0.0,
                    "w_off_ortg": 0.0,
                    "w_on_drtg": 0.0,
                    "w_off_drtg": 0.0,
                    "w_on_nrtg": 0.0,
                    "w_off_nrtg": 0.0,
                    "w_on_pace": 0.0
                }

            rec = agg[pid]
            rec["on_min"] += on_min
            rec["off_min"] += off_min
            rec["w_on_ortg"] += on_ortg * on_min
            rec["w_off_ortg"] += off_ortg * on_min
            rec["w_on_drtg"] += on_drtg * on_min
            rec["w_off_drtg"] += off_drtg * on_min
            rec["w_on_nrtg"] += on_nrtg * on_min
            rec["w_off_nrtg"] += off_nrtg * on_min
            rec["w_on_pace"] += on_pace * on_min

        time.sleep(0.65)

    players = []
    for pid, rec in agg.items():
        m_on = rec["on_min"]
        if m_on <= 0:
            continue
        on_ortg = round(rec["w_on_ortg"] / m_on, 1)
        off_ortg = round(rec["w_off_ortg"] / m_on, 1)
        diff_ortg = round(on_ortg - off_ortg, 1)

        on_drtg = round(rec["w_on_drtg"] / m_on, 1)
        off_drtg = round(rec["w_off_drtg"] / m_on, 1)
        diff_drtg = round(on_drtg - off_drtg, 1)

        on_nrtg = round(rec["w_on_nrtg"] / m_on, 1)
        off_nrtg = round(rec["w_off_nrtg"] / m_on, 1)
        diff_nrtg = round(on_nrtg - off_nrtg, 1)

        on_pace = round(rec["w_on_pace"] / m_on, 1)
        off_min = round(rec["off_min"], 1)
        on_min_r = round(m_on, 1)
        tot_team_min = on_min_r + off_min
        min_share = round(on_min_r / tot_team_min, 4) if tot_team_min > 0 else 0.0

        # oo array:
        # [0: ON_MIN, 1: OFF_MIN, 2: MIN_SHARE,
        #  3: ON_ORTG, 4: OFF_ORTG, 5: DIFF_ORTG,
        #  6: ON_DRTG, 7: OFF_DRTG, 8: DIFF_DRTG,
        #  9: ON_NRTG, 10: OFF_NRTG, 11: DIFF_NRTG,
        #  12: ON_PACE]
        oo_arr = [
            on_min_r, off_min, min_share,
            on_ortg, off_ortg, diff_ortg,
            on_drtg, off_drtg, diff_drtg,
            on_nrtg, off_nrtg, diff_nrtg,
            on_pace
        ]

        players.append({
            "id": pid,
            "n": rec["n"],
            "t": rec["t"],
            "pos": rec["pos"],
            "age": rec["age"],
            "gp": rec["gp"],
            "m": on_min_r,
            "oo": oo_arr
        })

    out_path = os.path.join(DATA_DIR, f"onoff-{season}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(players, f, separators=(",", ":"))
    print(f"  Saved {len(players)} players -> {out_path}")


if __name__ == "__main__":
    for season in SEASONS:
        try:
            build_on_off_season(season)
            build_rebounding_season(season)
            build_defense_season(season)
        except Exception as err:
            print(f"Skipping {season}: {err}")

    meta_path = os.path.join(DATA_DIR, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["updated"] = datetime.now(timezone.utc).isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
