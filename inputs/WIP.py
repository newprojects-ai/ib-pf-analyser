import requests, time, os, csv, io
from flask import Flask, render_template, request, redirect, url_for, flash, session
from webapp.models.watchlist import (
    get_watchlists, create_watchlist, add_to_watchlist, 
    remove_from_watchlist, delete_watchlist
)

# ... (keep all existing imports and configurations)

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

# ... (keep all existing routes until watchlists)

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
        if symbol_data['conid'] in selected_symbols:
            add_to_watchlist(watchlist_name, symbol_data)
            symbols_added += 1
    
    # Clear staging data
    session.pop('staging_data', None)
    
    flash(f'Successfully added {symbols_added} symbols to watchlist', 'success')
    return redirect(url_for('view_watchlist', name=watchlist_name))

# ... (keep all remaining routes)