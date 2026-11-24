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


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else current_season()
    print("Updating", season)
    z, r, p = fetch(season)
    DATA.mkdir(exist_ok=True)
    pos_path = DATA / "positions.json"
    pos = json.loads(pos_path.read_text()) if pos_path.exists() else {}
    for a, b in zip(p.PERSON_ID, p.POSITION):
        if isinstance(b, str) and b:
            pos[str(int(a))] = b[0]
    players = build(z, r, pos)
    if len(players) < 20:
        sys.exit(f"Only {len(players)} players returned; keeping existing data.")
    new = json.dumps(players, separators=(",", ":"), ensure_ascii=False)
    f = DATA / f"{season}.json"
    old = f.read_text(encoding="utf-8") if f.exists() else None
    pos_path.write_text(json.dumps(pos, separators=(",", ":")))
    if new == old:
        print("No changes since last update.")
        return
    f.write_text(new, encoding="utf-8")
    mp = DATA / "meta.json"
    meta = json.loads(mp.read_text()) if mp.exists() else {"seasons": []}
    if season not in meta["seasons"]:
        meta["seasons"].append(season)
    meta["seasons"].sort(reverse=True)
    meta["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    mp.write_text(json.dumps(meta))
    print(f"Wrote {len(players)} players to {f.name}")


if __name__ == "__main__":
    main()
