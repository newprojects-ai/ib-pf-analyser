import json
import os

WATCHLIST_FILE = 'webapp/data/watchlists.json'

def init_watchlists():
    if not os.path.exists('webapp/data'):
        os.makedirs('webapp/data')
    if not os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump({"watchlists": []}, f)

def get_watchlists():
    init_watchlists()
    with open(WATCHLIST_FILE, 'r') as f:
        return json.load(f)

def save_watchlists(watchlists):
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump(watchlists, f, indent=2)

def create_watchlist(name):
    watchlists = get_watchlists()
    watchlists["watchlists"].append({
        "name": name,
        "instruments": []
    })
    save_watchlists(watchlists)
    return watchlists

def add_to_watchlist(watchlist_name, instrument):
    watchlists = get_watchlists()
    for watchlist in watchlists["watchlists"]:
        if watchlist["name"] == watchlist_name:
            if instrument not in watchlist["instruments"]:
                watchlist["instruments"].append(instrument)
    save_watchlists(watchlists)
    return watchlists

def remove_from_watchlist(watchlist_name, instrument_id):
    watchlists = get_watchlists()
    for watchlist in watchlists["watchlists"]:
        if watchlist["name"] == watchlist_name:
            watchlist["instruments"] = [i for i in watchlist["instruments"] if i["conid"] != instrument_id]
    save_watchlists(watchlists)
    return watchlists

def delete_watchlist(watchlist_name):
    watchlists = get_watchlists()
    watchlists["watchlists"] = [w for w in watchlists["watchlists"] if w["name"] != watchlist_name]
    save_watchlists(watchlists)
    return watchlists