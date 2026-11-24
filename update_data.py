"""Pulls the current NBA season's shooting data and writes data/<season>.json.

Usage:  python update_data.py            (current season)
        python update_data.py 2025-26     (a specific season)
"""
import datetime, json, pathlib, sys, time

DATA = pathlib.Path(__file__).parent / "data"
PM = {"G": "Guard", "F": "Forward", "C": "Center"}
ZONES = ["Restricted Area", "In The Paint (Non-RA)", "Mid-Range",
         "Left Corner 3", "Right Corner 3", "Above the Break 3"]
RANGES = ["Overall", "Catch and Shoot", "Pullups", "Less Than 10 ft"]


def current_season(today=None):
    t = today or datetime.date.today()
    y = t.year if t.month >= 10 else t.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            print("  retrying after error:", e)
            time.sleep(5 * (i + 1))
    raise RuntimeError("NBA.com request failed after retries")


def fetch(season):
    import pandas as pd
    from nba_api.stats.endpoints import (LeagueDashPlayerShotLocations,
                                         LeagueDashPlayerPtShot, PlayerIndex)
    z = retry(lambda: LeagueDashPlayerShotLocations(
        season=season, distance_range="By Zone", per_mode_detailed="Totals",
        timeout=60).get_data_frames()[0])
    z.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c for c in z.columns]
    time.sleep(2)
    frames = []
    for rng in RANGES:
        df = retry(lambda: LeagueDashPlayerPtShot(
            season=season, per_mode_simple="Totals", general_range_nullable=rng,
            timeout=60).get_data_frames()[0])
        df["SHOT_RANGE"] = rng
        frames.append(df)
        time.sleep(2)
    p = retry(lambda: PlayerIndex(season=season, timeout=60).get_data_frames()[0])
    return z, pd.concat(frames), p


def build(z, r, pos):
    z = z.fillna(0)
    r = r.fillna(0)
    rg, meta = {}, {}
    for x in r.itertuples():
        pid = int(x.PLAYER_ID)
        rg.setdefault(pid, {})[x.SHOT_RANGE] = [
            int(x.FGM), int(x.FGA), int(x.FG2M), int(x.FG2A), int(x.FG3M), int(x.FG3A),
            round(x.FGA_FREQUENCY, 3), round(x.FG2A_FREQUENCY, 3), round(x.FG3A_FREQUENCY, 3)]
        if x.SHOT_RANGE == "Overall":
            meta[pid] = (int(x.AGE), int(x.GP), int(x.G))
    out = []
    for _, x in z.iterrows():
        pid = int(x.PLAYER_ID)
        if pid not in meta or meta[pid][1] < 1:
            continue
        out.append({"n": x.PLAYER_NAME, "t": x.TEAM_ABBREVIATION,
                    "age": meta[pid][0], "gp": meta[pid][1], "g": meta[pid][2],
                    "pos": PM.get(pos.get(str(pid), ""), ""),
                    "z": [[int(x[c + "_FGM"]), int(x[c + "_FGA"])] for c in ZONES],
                    "r": rg[pid]})
    return out


CATS = {  # defense category -> (FGM, FGA, FG%, normal FG%, diff) columns
    "Overall": ("D_FGM", "D_FGA", "D_FG_PCT", "NORMAL_FG_PCT", "PCT_PLUSMINUS"),
    "2 Pointers": ("FG2M", "FG2A", "FG2_PCT", "NS_FG2_PCT", "PLUSMINUS"),
    "3 Pointers": ("FG3M", "FG3A", "FG3_PCT", "NS_FG3_PCT", "PLUSMINUS"),
    "Less Than 6Ft": ("FGM_LT_06", "FGA_LT_06", "LT_06_PCT", "NS_LT_06_PCT", "PLUSMINUS"),
    "Greater Than 15Ft": ("FGM_GT_15", "FGA_GT_15", "GT_15_PCT", "NS_GT_15_PCT", "PLUSMINUS"),
}


def fetch_defense(season):
    import pandas as pd
    from nba_api.stats.endpoints import (LeagueDashPtDefend, LeagueDashPlayerStats,
                                         LeagueHustleStatsPlayer)
    frames = []
    for cat in CATS:
        df = retry(lambda: LeagueDashPtDefend(
            season=season, defense_category=cat, per_mode_simple="Totals",
            timeout=60).get_data_frames()[0])
        df["DEFENSE_CATEGORY"] = cat
        frames.append(df)
        time.sleep(2)
    adv = retry(lambda: LeagueDashPlayerStats(
        season=season, measure_type_detailed_defense="Defense", per_mode_detailed="Totals",
        timeout=60).get_data_frames()[0])
    time.sleep(2)
    hu = retry(lambda: LeagueHustleStatsPlayer(
        season=season, per_mode_time="Totals", timeout=60).get_data_frames()[0])
    return pd.concat(frames), adv, hu


def _n(v, nd=3):
    if v is None or v != v:
        return None
    return int(round(float(v))) if nd == 0 else round(float(v), nd)


def build_defense(rg, adv, hu, pos):
    A = {int(x.PLAYER_ID): x for x in adv.itertuples()}
    H = {int(x.PLAYER_ID): x for x in hu.itertuples()}
    base = {}
    for x in rg.itertuples():
        pid = int(x.CLOSE_DEF_PERSON_ID)
        cols = CATS.get(x.DEFENSE_CATEGORY)
        if not cols or getattr(x, cols[1]) != getattr(x, cols[1]):
            continue
        p = base.get(pid)
        if p is None:
            pl = x.PLAYER_POSITION[:1] if isinstance(x.PLAYER_POSITION, str) else pos.get(str(pid), "")
            a, h = A.get(pid), H.get(pid)
            p = base[pid] = {
                "n": x.PLAYER_NAME, "t": x.PLAYER_LAST_TEAM_ABBREVIATION,
                "age": int(x.AGE) if x.AGE == x.AGE else 0, "gp": int(x.GP), "g": int(x.G),
                "pos": PM.get(pl, ""), "m": _n(a.MIN, 1) if a else None,
                "d": [_n(a.DEF_RATING, 1), _n(a.DREB, 0), _n(a.DREB_PCT), _n(a.STL, 0), _n(a.PCT_STL),
                      _n(a.BLK, 0), _n(a.PCT_BLK), _n(a.DEF_WS, 2)] if a else [None] * 8,
                "r": {}}
            p["d"] += [_n(h.CONTESTED_SHOTS, 0), _n(h.DEFLECTIONS, 0), _n(h.CHARGES_DRAWN, 0)] if h else [None] * 3
        v = [getattr(x, c) for c in cols]
        p["r"][x.DEFENSE_CATEGORY] = [int(v[0]), int(v[1]), _n(v[2]), _n(v[3]), _n(v[4]), _n(x.FREQ)]
    return list(base.values())


def write_if_changed(path, text):
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if text == old:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else current_season()
    print("Updating", season)
    DATA.mkdir(exist_ok=True)
    z, r, p = fetch(season)
    pos_path = DATA / "positions.json"
    pos = json.loads(pos_path.read_text()) if pos_path.exists() else {}
    for a, b in zip(p.PERSON_ID, p.POSITION):
        if isinstance(b, str) and b:
            pos[str(int(a))] = b[0]
    players = build(z, r, pos)
    if len(players) < 20:
        sys.exit(f"Only {len(players)} players returned; keeping existing data.")
    pos_path.write_text(json.dumps(pos, separators=(",", ":")))
    changed = write_if_changed(DATA / f"{season}.json",
                               json.dumps(players, separators=(",", ":"), ensure_ascii=False))
    print(f"Shooting: {len(players)} players" + ("" if changed else " (no changes)"))
    try:  # a defense failure should not block the shooting update
        time.sleep(2)
        dp = build_defense(*fetch_defense(season), pos)
        if len(dp) < 20:
            raise RuntimeError(f"only {len(dp)} defenders returned")
        dc = write_if_changed(DATA / f"defense-{season}.json",
                              json.dumps(dp, separators=(",", ":"), ensure_ascii=False))
        print(f"Defense: {len(dp)} players" + ("" if dc else " (no changes)"))
        changed = changed or dc
    except Exception as e:
        print("Defense update skipped:", e)
    if not changed:
        print("No changes since last update.")
        return
    mp = DATA / "meta.json"
    meta = json.loads(mp.read_text()) if mp.exists() else {"seasons": []}
    if season not in meta["seasons"]:
        meta["seasons"].append(season)
    meta["seasons"].sort(reverse=True)
    meta["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    mp.write_text(json.dumps(meta))
    print("Data updated.")


if __name__ == "__main__":
    main()
