import requests, time, os, csv, io
from flask import Flask, render_template, request, redirect, url_for, flash, session
from webapp.models.watchlist import (
    get_watchlists, create_watchlist, add_to_watchlist, 
    remove_from_watchlist, delete_watchlist
)

# disable warnings until you install a certificate
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_API_URL = "https://localhost:5055/v1/api"
ACCOUNT_ID = os.environ.get('IBKR_ACCOUNT_ID')

os.environ['PYTHONHTTPSVERIFY'] = '0'

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for flash messages and session

@app.template_filter('ctime')
def timectime(s):
    return time.ctime(s/1000)

def check_auth():
    """Check if user is authenticated with IBKR"""
    try:
        r = requests.get(f"{BASE_API_URL}/portfolio/accounts", verify=False)
        return r.status_code == 200 and r.content and 'error' not in r.json()
    except:
        return False

def get_account_id():
    """Get the first available account ID"""
    try:
        r = requests.get(f"{BASE_API_URL}/portfolio/accounts", verify=False)
        if r.status_code == 200 and r.content:
            accounts = r.json()
            if accounts and len(accounts) > 0:
                return accounts[0]['id']
    except:
        pass
    return ACCOUNT_ID

def process_csv_content(content):
    """Process CSV content and return list of symbols"""
    symbols = []
    try:
        # Try first with automatic dialect detection
        dialect = csv.Sniffer().sniff(content)
        has_header = csv.Sniffer().has_header(content)
        
        # Read CSV content
        lines = content.splitlines()
        reader = csv.reader(lines, dialect)
        
        # If has header, process accordingly
        if has_header:
            headers = next(reader)
            # Try to find symbol column
            symbol_col = None
            for i, header in enumerate(headers):
                if header.lower().strip() in ['symbol', 'symbols', 'ticker', 'tickers']:
                    symbol_col = i
                    break
            
            if symbol_col is not None:
                for row in reader:
                    if len(row) > symbol_col:
                        symbol = row[symbol_col].strip().upper()
                        if symbol:
                            symbols.append(symbol)
            else:
                # If no header found, assume first column contains symbols
                for row in reader:
                    if row:
                        symbol = row[0].strip().upper()
                        if symbol:
                            symbols.append(symbol)
        else:
            # No header, assume first column contains symbols
            for row in reader:
                if row:
                    symbol = row[0].strip().upper()
                    if symbol:
                        symbols.append(symbol)
                        
    except Exception as e:
        # If CSV parsing fails, try simple line-by-line reading
        lines = content.splitlines()
        for line in lines:
            symbol = line.strip().upper()
            if symbol and not symbol.lower().startswith('symbol'):  # Skip if looks like header
                symbols.append(symbol)
    
    return list(set(symbols))  # Remove duplicates

@app.route("/")
def dashboard():
    try:
        r = requests.get(f"{BASE_API_URL}/portfolio/accounts", verify=False)
        accounts = r.json()
    except Exception as e:
        return 'Make sure you authenticate first then visit this page. <a href="https://localhost:5055">Log in</a>'

    account = accounts[0]
    account_id = accounts[0]["id"]
    r = requests.get(f"{BASE_API_URL}/portfolio/{account_id}/summary", verify=False)
    summary = r.json()
    
    return render_template("dashboard.html", account=account, summary=summary)

@app.route("/lookup")
def lookup():
    symbol = request.args.get('symbol', None)
    stocks = []

    if symbol is not None:
        r = requests.get(f"{BASE_API_URL}/iserver/secdef/search?symbol={symbol}&name=true", verify=False)
        response = r.json()
        stocks = response

    return render_template("lookup.html", stocks=stocks)

@app.route("/contract/<contract_id>/<period>")
def contract(contract_id, period='5d', bar='1d'):
    data = {
        "conids": [
            contract_id
        ]
    }
    
    r = requests.post(f"{BASE_API_URL}/trsrv/secdef", data=data, verify=False)
    contract = r.json()['secdef'][0]

    r = requests.get(f"{BASE_API_URL}/iserver/marketdata/history?conid={contract_id}&period={period}&bar={bar}", verify=False)
    price_history = r.json()

    return render_template("contract.html", price_history=price_history, contract=contract)

@app.route("/orders")
def orders():
    try:
        r = requests.get(f"{BASE_API_URL}/iserver/account/orders", verify=False)
        if r.status_code == 200:
            orders = r.json().get("orders", [])
        else:
            orders = []
    except Exception as e:
        orders = []
    return render_template("orders.html", orders=orders)

@app.route("/order", methods=['POST'])
def place_order():
    account_id = get_account_id()
    if not account_id:
        flash("Unable to determine account ID", "error")
        return redirect("/orders")

    data = {
        "orders": [
            {
                "conid": int(request.form.get('contract_id')),
                "orderType": "LMT",
                "price": float(request.form.get('price')),
                "quantity": int(request.form.get('quantity')),
                "side": request.form.get('side'),
                "tif": "GTC"
            }
        ]
    }

    r = requests.post(f"{BASE_API_URL}/iserver/account/{account_id}/orders", json=data, verify=False)
    return redirect("/orders")

@app.route("/orders/<order_id>/cancel")
def cancel_order(order_id):
    account_id = get_account_id()
    if not account_id:
        flash("Unable to determine account ID", "error")
        return redirect("/orders")

    cancel_url = f"{BASE_API_URL}/iserver/account/{account_id}/order/{order_id}" 
    r = requests.delete(cancel_url, verify=False)
    return r.json()

@app.route("/portfolio")
def portfolio():
    if not check_auth():
        flash("Please authenticate first", "error")
        return render_template("portfolio.html", positions=[], auth_error=True)

    account_id = get_account_id()
    if not account_id:
        flash("Unable to determine account ID", "error")
        return render_template("portfolio.html", positions=[], auth_error=True)

    try:
        # Get positions with retry logic
        for _ in range(3):  # Try up to 3 times
            positions_response = requests.get(f"{BASE_API_URL}/portfolio/{account_id}/positions/0", verify=False)
            
            if positions_response.status_code == 200 and positions_response.content:
                try:
                    positions = positions_response.json()
                    if isinstance(positions, list):
                        if not positions:
                            flash("No positions found in your portfolio", "info")
                        return render_template("portfolio.html", positions=positions, auth_error=False)
                except ValueError:
                    time.sleep(1)  # Wait before retry
                    continue
            
            time.sleep(1)  # Wait before retry

        flash("Error fetching positions. Please try again.", "error")
        return render_template("portfolio.html", positions=[], auth_error=False)

    except requests.exceptions.RequestException as e:
        flash(f"Error connecting to Interactive Brokers API: {str(e)}", "error")
        return render_template("portfolio.html", positions=[], auth_error=True)

@app.route("/scanner")
def scanner():
    r = requests.get(f"{BASE_API_URL}/iserver/scanner/params", verify=False)
    params = r.json()

    scanner_map = {}
    filter_map = {}

    for item in params['instrument_list']:
        scanner_map[item['type']] = {
            "display_name": item['display_name'],
            "filters": item['filters'],
            "sorts": []
        }

    for item in params['filter_list']:
        filter_map[item['group']] = {
            "display_name": item['display_name'],
            "type": item['type'],
            "code": item['code']
        }

    for item in params['scan_type_list']:
        for instrument in item['instruments']:
            scanner_map[instrument]['sorts'].append({
                "name": item['display_name'],
                "code": item['code']
            })

    for item in params['location_tree']:
        scanner_map[item['type']]['locations'] = item['locations']

    submitted = request.args.get("submitted", "")
    selected_instrument = request.args.get("instrument", "")
    location = request.args.get("location", "")
    sort = request.args.get("sort", "")
    scan_results = []
    filter_code = request.args.get("filter", "")
    filter_value = request.args.get("filter_value", "")

    if submitted:
        print("submitting")
        data = {
            "instrument": selected_instrument,
            "location": location,
            "type": sort,
            "filter": [
                {
                    "code": filter_code,
                    "value": filter_value
                }
            ]
        }
            
        r = requests.post(f"{BASE_API_URL}/iserver/scanner/run", json=data, verify=False)
        scan_results = r.json()

    return render_template("scanner.html", params=params, scanner_map=scanner_map, filter_map=filter_map, scan_results=scan_results)

@app.route("/watchlists")
def watchlists():
    sort_by = request.args.get('sort_by')
    filter_by = {
        'price_min': request.args.get('price_min'),
        'price_max': request.args.get('price_max'),
        'change_min': request.args.get('change_min'),
        'change_max': request.args.get('change_max')
    }
    filter_by = {k: v for k, v in filter_by.items() if v}  # Remove empty filters
    
    return render_template(
        "watchlists.html", 
        watchlists=get_watchlists(sort_by=sort_by, filter_by=filter_by if filter_by else None), 
        selected_watchlist=None
    )

@app.route("/watchlists/<name>")
def view_watchlist(name):
    sort_by = request.args.get('sort_by')
    filter_by = {
        'price_min': request.args.get('price_min'),
        'price_max': request.args.get('price_max'),
        'change_min': request.args.get('change_min'),
        'change_max': request.args.get('change_max')
    }
    filter_by = {k: v for k, v in filter_by.items() if v}  # Remove empty filters
    
    watchlists = get_watchlists(sort_by=sort_by, filter_by=filter_by if filter_by else None)
    selected = next((w for w in watchlists["watchlists"] if w["name"] == name), None)
    search_results = request.args.get("search_results", None)
    return render_template("watchlists.html", watchlists=watchlists, selected_watchlist=selected, search_results=search_results)

@app.route("/watchlists/create", methods=["POST"])
def create_watchlist_route():
    name = request.form.get("watchlist_name")
    if name:
        create_watchlist(name)
        flash(f"Watchlist '{name}' created successfully", "success")
    return redirect(url_for("watchlists"))

@app.route("/watchlists/<watchlist_name>/search")
def search_for_watchlist(watchlist_name):
    symbol = request.args.get('symbol', None)
    search_results = []
    
    if symbol:
        r = requests.get(f"{BASE_API_URL}/iserver/secdef/search?symbol={symbol}&name=true", verify=False)
        search_results = r.json()
    
    watchlists = get_watchlists()
    selected = next((w for w in watchlists["watchlists"] if w["name"] == watchlist_name), None)
    
    return render_template("watchlists.html", 
                         watchlists=watchlists, 
                         selected_watchlist=selected, 
                         search_results=search_results)

@app.route("/watchlists/<watchlist_name>/add", methods=["POST"])
def add_to_watchlist_route(watchlist_name):
    instrument = {
        "symbol": request.form.get("symbol"),
        "conid": request.form.get("conid"),
        "company_name": request.form.get("company_name")
    }
    add_to_watchlist(watchlist_name, instrument)
    flash(f"Added {instrument['symbol']} to watchlist", "success")
    return redirect(url_for("view_watchlist", name=watchlist_name))

@app.route("/watchlists/<watchlist_name>/remove/<instrument_id>")
def remove_from_watchlist_route(watchlist_name, instrument_id):
    remove_from_watchlist(watchlist_name, instrument_id)
    flash("Symbol removed from watchlist", "success")
    return redirect(url_for("view_watchlist", name=watchlist_name))

@app.route("/watchlists/<name>/delete")
def delete_watchlist_route(name):
    delete_watchlist(name)
    flash(f"Watchlist '{name}' deleted", "success")
    return redirect(url_for("watchlists"))

@app.route("/watchlists/<watchlist_name>/upload", methods=["POST"])
def upload_csv_watchlist(watchlist_name):
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('view_watchlist', name=watchlist_name))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('view_watchlist', name=watchlist_name))
    
    if not file.filename.endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return redirect(url_for('view_watchlist', name=watchlist_name))
    
    try:
        # Read file content
        content = file.stream.read().decode('UTF-8')
        if not content.strip():
            flash('The uploaded file is empty', 'error')
            return redirect(url_for('view_watchlist', name=watchlist_name))
        
        # Process CSV content
        symbols = process_csv_content(content)
        
        if not symbols:
            flash('No valid symbols found in the file', 'error')
            return redirect(url_for('view_watchlist', name=watchlist_name))
        
        successful_symbols = []
        failed_symbols = []
        
        for symbol in symbols:
            try:
                # Search for the symbol
                r = requests.get(f"{BASE_API_URL}/iserver/secdef/search?symbol={symbol}&name=true", verify=False)
                results = r.json()
                
                if results and len(results) > 0:
                    # Take the first match
                    stock = results[0]
                    successful_symbols.append({
                        "symbol": stock['symbol'],
                        "conid": stock['conid'],
                        "company_name": stock.get('companyName', ''),
                        "description": stock.get('description', '')
                    })
                else:
                    failed_symbols.append({
                        "symbol": symbol,
                        "reason": "Symbol not found"
                    })
            except Exception as e:
                failed_symbols.append({
                    "symbol": symbol,
                    "reason": str(e)
                })
                continue
        
        # Store in session for the staging page
        session['staging_data'] = {
            'watchlist_name': watchlist_name,
            'successful_symbols': successful_symbols,
            'failed_symbols': failed_symbols
        }
        
        return redirect(url_for('stage_csv_upload', watchlist_name=watchlist_name))
            
    except Exception as e:
        flash(f'Error processing CSV file: {str(e)}', 'error')
        return redirect(url_for('view_watchlist', name=watchlist_name))

@app.route("/watchlists/<watchlist_name>/stage", methods=["GET"])
def stage_csv_upload(watchlist_name):
    staging_data = session.get('staging_data', {})
    
    if not staging_data or staging_data.get('watchlist_name') != watchlist_name:
        flash('No staging data found. Please upload a CSV file first.', 'error')
        return redirect(url_for('view_watchlist', name=watchlist_name))
    
    watchlists = get_watchlists()
    selected = next((w for w in watchlists["watchlists"] if w["name"] == watchlist_name), None)
    
    return render_template(
        "watchlists_staging.html",
        watchlists=watchlists,
        selected_watchlist=selected,
        successful_symbols=staging_data.get('successful_symbols', []),
        failed_symbols=staging_data.get('failed_symbols', [])
    )

@app.route("/watchlists/<watchlist_name>/stage/confirm", methods=["POST"])
def confirm_staged_symbols(watchlist_name):
    staging_data = session.get('staging_data', {})
    
    if not staging_data or staging_data.get('watchlist_name') != watchlist_name:
        flash('No staging data found. Please upload a CSV file first.', 'error')
        return redirect(url_for('view_watchlist', name=watchlist_name))
    
    selected_symbols = request.form.getlist('selected_symbols')
    successful_symbols = staging_data.get('successful_symbols', [])
    
    symbols_added = 0
    for symbol_data in successful_symbols:
        if str(symbol_data['conid']) in selected_symbols:
            add_to_watchlist(watchlist_name, symbol_data)
            symbols_added += 1
    
    # Clear staging data
    session.pop('staging_data', None)
    
    flash(f'Successfully added {symbols_added} symbols to watchlist', 'success')
    return redirect(url_for('view_watchlist', name=watchlist_name))