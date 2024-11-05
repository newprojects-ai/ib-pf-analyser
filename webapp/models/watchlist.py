import json
import os
import requests
from datetime import datetime

WATCHLIST_FILE = 'webapp/data/watchlists.json'
BASE_API_URL = "https://localhost:5055/v1/api"

def init_watchlists():
    if not os.path.exists('webapp/data'):
        os.makedirs('webapp/data')
    if not os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump({"watchlists": []}, f)

def get_watchlists(sort_by=None, filter_by=None):
    init_watchlists()
    with open(WATCHLIST_FILE, 'r') as f:
        watchlists = json.load(f)
    
    # Update prices for all instruments
    for watchlist in watchlists["watchlists"]:
        for instrument in watchlist["instruments"]:
            update_instrument_price(instrument)
    
    if sort_by and watchlists["watchlists"]:
        for watchlist in watchlists["watchlists"]:
            watchlist["instruments"].sort(
                key=lambda x: (x.get(sort_by, ""), x["symbol"]),
                reverse=sort_by in ["price", "price_change_pct"]
            )
    
    if filter_by:
        for watchlist in watchlists["watchlists"]:
            watchlist["instruments"] = [
                i for i in watchlist["instruments"]
                if matches_filter(i, filter_by)
            ]
    
    return watchlists

def matches_filter(instrument, filter_by):
    if filter_by.get("price_min") and instrument.get("price", 0) < float(filter_by["price_min"]):
        return False
    if filter_by.get("price_max") and instrument.get("price", 0) > float(filter_by["price_max"]):
        return False
    if filter_by.get("change_min") and instrument.get("price_change_pct", 0) < float(filter_by["change_min"]):
        return False
    if filter_by.get("change_max") and instrument.get("price_change_pct", 0) > float(filter_by["change_max"]):
        return False
    return True

def update_instrument_price(instrument):
    try:
        r = requests.get(
            f"{BASE_API_URL}/iserver/marketdata/snapshot?conids={instrument['conid']}", 
            verify=False
        )
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                market_data = data[0]
                instrument["price"] = market_data.get("31", 0)  # Last price
                instrument["price_change"] = market_data.get("32", 0)  # Change
                instrument["price_change_pct"] = market_data.get("33", 0)  # Change %
                instrument["volume"] = market_data.get("34", 0)  # Volume
                instrument["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error updating price for {instrument['symbol']}: {str(e)}")

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
                update_instrument_price(instrument)
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