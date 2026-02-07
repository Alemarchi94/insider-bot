import requests
import json
import os
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import time
import re
from collections import defaultdict

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['CHAT_ID']
SEEN_FILE = 'seen_transactions.json'
CACHE_13F_FILE = 'cache_13f.json'

HEADERS = {
    'User-Agent': 'Alessandro Marchi alessandro94marchi@gmail.com',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

NOTABLE_INVESTORS = [
    'berkshire hathaway', 'warren buffett', 'scion', 'michael burry', 'burry',
    'bill ackman', 'pershing square', 'carl icahn', 'icahn enterprises',
    'bridgewater', 'ray dalio', 'renaissance technologies', 'citadel', 'ken griffin',
    'tiger global', 'coatue', 'greenlight', 'david einhorn', 'baupost', 'seth klarman',
    'third point', 'dan loeb', 'elliott management', 'paul singer', 'appaloosa',
    'david tepper', 'lone pine', 'viking global', 'millennium', 'point72', 'steve cohen',
    'two sigma', 'de shaw', 'aqr', 'paulson', 'john paulson', 'soros', 'george soros',
    'stanley druckenmiller', 'duquesne', 'bill miller', 'bill gates', 'cascade investment',
    'jeff bezos', 'mark zuckerberg', 'elon musk', 'larry ellison', 'jim simons',
    'chase coleman', 'sequoia', 'a16z', 'andreessen horowitz'
]

def load_json_file(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_json_file(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f)

def load_seen():
    data = load_json_file(SEEN_FILE)
    if isinstance(data, dict):
        return set(data.get('seen', []))
    elif isinstance(data, list):
        return set(data)
    else:
        return set()

def save_seen(seen):
    save_json_file(SEEN_FILE, {'seen': list(seen)})

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        # Split long messages
        if len(message) > 4096:
            parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for part in parts:
                requests.post(url, json={
                    'chat_id': CHAT_ID,
                    'text': part,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True
                })
                time.sleep(0.5)
        else:
            requests.post(url, json={...}, timeout=10)
                'chat_id': CHAT_ID,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            })
        return True
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def format_number(num):
    """Formatta numeri grandi"""
    if num >= 1_000_000_000:
        return f"${num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"${num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"${num/1_000:.0f}K"
    else:
        return f"${num:.0f}"

def parse_amount_range(amount_str):
    ranges = {
        '$1,001 - $15,000': '$8K',
        '$15,001 - $50,000': '$32K',
        '$50,001 - $100,000': '$75K',
        '$100,001 - $250,000': '$175K',
        '$250,001 - $500,000': '$375K',
        '$500,001 - $1,000,000': '$750K',
        '$1,000,001 - $5,000,000': '$3M',
        '$5,000,001 - $25,000,000': '$15M',
        '$25,000,001 - $50,000,000': '$37M',
        'Over $50,000,000': '>$50M'
    }
    return ranges.get(amount_str, amount_str)

def extract_ticker_from_title(title):
    match = re.search(r'\(([A-Z]{1,5})\)', title)
    return match.group(1) if match else None

def extract_company_from_title(title):
    title = re.sub(r'^(3|4|5|SC 13[DG](/A)?|13F-HR)\s*-\s*', '', title)
    return title.split('(')[0].strip()

def is_notable_investor(title):
    title_lower = title.lower()
    return any(name in title_lower for name in NOTABLE_INVESTORS)

def is_tax_payment(trade):
    comment = str(trade.get('comment', '')).lower()
    return any(kw in comment for kw in ['tax', 'withholding', 'tax obligation'])

def check_congressional_trades():
    url = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
    try:
        response = requests.get(url, timeout=10)
        trades = response.json()
        cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        return [t for t in trades if t.get('disclosure_date', '') >= cutoff]
    except:
        return []

def check_senate_trades():
    url = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"
    try:
        response = requests.get(url, timeout=10)
        trades = response.json()
        cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        return [t for t in trades if t.get('disclosure_date', '') >= cutoff]
    except:
        return []

def check_sec_filings(form_type, days_back=2, count=100):
    filings = []
    try:
        url = "https://www.sec.gov/cgi-bin/browse-edgar"
        for days_ago in range(days_back):
            date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y%m%d')
            params = {
                'action': 'getcurrent',
                'type': form_type,
                'company': '',
                'dateb': date,
                'owner': 'include',
                'start': 0,
                'count': count,
                'output': 'atom'
            }
            time.sleep(0.15)
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                continue
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns):
                try:
                    filings.append({
                        'title': entry.find('atom:title', ns).text,
                        'link': entry.find('atom:link', ns).attrib['href'],
                        'date': entry.find('atom:updated', ns).text[:10],
                        'type': form_type
                    })
                except:
                    continue
        return filings
    except Exception as e:
        print(f"Form {form_type} error: {e}")
        return []

def parse_13f_xml(filing_url):
    """
    Scarica e parsa un filing 13F-HR dalla SEC
    Ritorna dict: {ticker: {'shares': N, 'value': $, 'name': ...}}
    """
    try:
        # Il link atom punta alla pagina index, dobbiamo trovare il file .xml
        time.sleep(0.15)
        response = requests.get(filing_url, headers=HEADERS, timeout=20)
        
        # Cerca il link al file informationtable.xml o primary_doc.xml
        xml_pattern = re.search(r'href="(/Archives/edgar/data/\d+/\d+/[^"]+\.xml)"', response.text)
        
        if not xml_pattern:
            print(f"   No XML found in {filing_url}")
            return {}
        
        xml_url = "https://www.sec.gov" + xml_pattern.group(1)
        
        time.sleep(0.15)
        xml_response = requests.get(xml_url, headers=HEADERS, timeout=20)
        
        # Parse XML
        root = ET.fromstring(xml_response.content)
        
        holdings = {}
        
        # Namespace può variare
        ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
        
        # Cerca <infoTable> elements
        for info_table in root.findall('.//infoTable') or root.findall('.//{*}infoTable'):
            try:
                name_elem = info_table.find('.//nameOfIssuer') or info_table.find('.//{*}nameOfIssuer')
                ticker_elem = info_table.find('.//cusip') or info_table.find('.//{*}cusip')
                shares_elem = info_table.find('.//shrsOrPrnAmt/sshPrnamt') or info_table.find('.//{*}sshPrnamt')
                value_elem = info_table.find('.//value') or info_table.find('.//{*}value')
                
                if not all([name_elem, shares_elem, value_elem]):
                    continue
                
                name = name_elem.text.strip() if name_elem.text else "Unknown"
                cusip = ticker_elem.text.strip() if ticker_elem.text else ""
                shares = int(shares_elem.text) if shares_elem.text else 0
                value = int(value_elem.text) * 1000 if value_elem.text else 0  # SEC reports in thousands
                
                # Converti CUSIP in ticker (approssimazione - usa il nome company)
                ticker = cusip[:6].upper()  # CUSIP primi 6 char
                
                holdings[ticker] = {
                    'name': name,
                    'shares': shares,
                    'value': value,
                    'cusip': cusip
                }
            except Exception as e:
                continue
        
        return holdings
    
    except Exception as e:
        print(f"   Error parsing 13F XML: {e}")
        return {}

def compare_13f_holdings(current, previous):
    """
    Confronta 2 holdings 13F e ritorna: new, increased, decreased, closed
    """
    changes = {
        'new': [],        # Nuove posizioni
        'increased': [],  # Aumentate
        'decreased': [],  # Diminuite
        'closed': []      # Chiuse
    }
    
    # Nuove e modificate
    for ticker, curr_data in current.items():
        if ticker not in previous:
            changes['new'].append((ticker, curr_data))
        else:
            prev_value = previous[ticker]['value']
            curr_value = curr_data['value']
            change_pct = ((curr_value - prev_value) / prev_value * 100) if prev_value > 0 else 0
            
            if abs(change_pct) >= 25:  # Solo variazioni significative >25%
                if change_pct > 0:
                    changes['increased'].append((ticker, curr_data, change_pct))
                else:
                    changes['decreased'].append((ticker, curr_data, change_pct))
    
    # Chiuse
    for ticker, prev_data in previous.items():
        if ticker not in current:
            changes['closed'].append((ticker, prev_data))
    
    return changes

def format_congressional_message(trade, source):
    owner = trade.get('representative', trade.get('senator', 'N/A'))
    ticker = trade.get('ticker', 'N/A')
    amount = parse_amount_range(trade.get('amount', 'N/A'))
    tx_type = trade.get('type', 'N/A')
    date = trade.get('transaction_date', trade.get('disclosure_date', 'N/A'))
    
    if 'purchase' in tx_type.lower():
        action_emoji = "🟢 ACQUISTO"
    elif 'sale' in tx_type.lower():
        action_emoji = "🔴 VENDITA"
    else:
        action_emoji = "📊 " + tx_type.upper()
    
    vips = ['pelosi', 'trump', 'mcconnell', 'schumer', 'biden', 'warren']
    header = "⭐️ VIP POLITICO ⭐️" if any(v in owner.lower() for v in vips) else "🏛 POLITICO"
    
    return f"""{header}

👤 Nome: <b>{owner}</b>
🏢 Ruolo: Politico ({source})

{action_emoji}
📊 Ticker: <b>{ticker}</b>
💰 Valore: {amount}
📅 Data: {date}

{trade.get('comment', '')}"""

def format_insider_form4_message(filing):
    title = filing['title']
    company = extract_company_from_title(title)
    ticker = extract_ticker_from_title(title)
    
    emoji = {"3": "🆕", "4": "📋", "5": "📅"}.get(filing['type'], "📄")
    desc = {"3": "NUOVO INSIDER", "4": "INSIDER TRADING", "5": "REPORT ANNUALE"}.get(filing['type'], "FILING")
    
    msg = f"""{emoji} <b>{desc}</b>

🏢 Company: <b>{company}</b>"""
    if ticker:
        msg += f"\n📊 Ticker: <b>{ticker}</b>"
    
    msg += f"""
👤 Ruolo: Insider/Executive
📅 Data: {filing['date']}

🔗 <a href="{filing['link']}">Dettagli SEC</a>"""
    
    return msg

def format_form13dg_message(filing):
    title = filing['title']
    company = extract_company_from_title(title)
    ticker = extract_ticker_from_title(title)
    
    parts = title.split(' - ')
    investor = parts[1].split('(')[0].strip() if len(parts) > 1 else "Investitore"
    
    is_notable = is_notable_investor(title)
    is_amendment = '/A' in filing['type']
    
    emoji = "📊" if is_amendment else "🚨"
    desc = "MODIFICA POSIZIONE" if is_amendment else "ACQUISIZIONE >5%"
    header = "⭐️⭐️ INVESTITORE FAMOSO ⭐️⭐️\n" if is_notable else ""
    
    msg = f"""{header}{emoji} <b>{desc}</b>

👤 Investitore: <b>{investor}</b>
🏢 Ruolo: Fondo/Istituzionale
🎯 Target: <b>{company}</b>"""
    
    if ticker:
        msg += f"\n📊 Ticker: <b>{ticker}</b>"
    
    msg += f"""
📅 Data: {filing['date']}

🔗 <a href="{filing['link']}">% esatta e dettagli</a>"""
    
    return msg

def format_13f_detailed_message(fund_name, changes, total_value):
    """Formato dettagliato per 13F con parsing completo"""
    
    msg = f"""⭐️⭐️ <b>13F - HOLDINGS TRIMESTRALE</b> ⭐️⭐️

👤 Fondo: <b>{fund_name}</b>
🏢 Ruolo: Investitore istituzionale
💼 Valore totale portfolio: <b>{format_number(total_value)}</b>

"""
    
    # Nuove posizioni
    if changes['new']:
        msg += "🆕 <b>NUOVE POSIZIONI</b>\n"
        # Ordina per valore e prendi le top 10
        top_new = sorted(changes['new'], key=lambda x: x[1]['value'], reverse=True)[:10]
        for ticker, data in top_new:
            pct = (data['value'] / total_value * 100) if total_value > 0 else 0
            msg += f"  • <b>{ticker}</b> - {data['name'][:30]}\n"
            msg += f"    💰 {format_number(data['value'])} ({pct:.1f}% ptf) | {data['shares']:,} azioni\n"
        if len(changes['new']) > 10:
            msg += f"  ... e altre {len(changes['new']) - 10} nuove posizioni\n"
        msg += "\n"
    
    # Aumenti significativi
    if changes['increased']:
        msg += "📈 <b>AUMENTI SIGNIFICATIVI (&gt;25%)</b>\n"
        top_inc = sorted(changes['increased'], key=lambda x: abs(x[2]), reverse=True)[:8]
        for ticker, data, change_pct in top_inc:
            pct = (data['value'] / total_value * 100) if total_value > 0 else 0
            msg += f"  • <b>{ticker}</b> - {data['name'][:30]}\n"
            msg += f"    📊 +{change_pct:.0f}% | {format_number(data['value'])} ({pct:.1f}% ptf)\n"
        if len(changes['increased']) > 8:
            msg += f"  ... e altri {len(changes['increased']) - 8} aumenti\n"
        msg += "\n"
    
    # Riduzioni significative
    if changes['decreased']:
        msg += "📉 <b>RIDUZIONI SIGNIFICATIVE (&gt;25%)</b>\n"
        top_dec = sorted(changes['decreased'], key=lambda x: abs(x[2]), reverse=True)[:8]
        for ticker, data, change_pct in top_dec:
            pct = (data['value'] / total_value * 100) if total_value > 0 else 0
            msg += f"  • <b>{ticker}</b> - {data['name'][:30]}\n"
            msg += f"    📊 {change_pct:.0f}% | {format_number(data['value'])} ({pct:.1f}% ptf)\n"
        if len(changes['decreased']) > 8:
            msg += f"  ... e altre {len(changes['decreased']) - 8} riduzioni\n"
        msg += "\n"
    
    # Posizioni chiuse
    if changes['closed']:
        msg += "❌ <b>POSIZIONI CHIUSE</b>\n"
        top_closed = sorted(changes['closed'], key=lambda x: x[1]['value'], reverse=True)[:8]
        for ticker, data in top_closed:
            msg += f"  • <b>{ticker}</b> - {data['name'][:30]} ({format_number(data['value'])})\n"
        if len(changes['closed']) > 8:
            msg += f"  ... e altre {len(changes['closed']) - 8} chiusure\n"
    
    if not any([changes['new'], changes['increased'], changes['decreased'], changes['closed']]):
        msg += "ℹ️ Nessuna variazione significativa rispetto al trimestre precedente"
    
    return msg

def main():
    seen = load_seen()
    new_seen = seen.copy()
    cache_13f = load_json_file(CACHE_13F_FILE)
    sent_count = 0
    
    print(f"\n{'='*60}")
    print(f"🤖 INSIDER BOT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Congressional
    print("📊 Congressional...")
    for trade in check_congressional_trades() + check_senate_trades():
        source = 'House' if 'representative' in trade else 'Senate'
        trade_id = f"{source}_{trade.get('representative', trade.get('senator'))}_{trade.get('ticker')}_{trade.get('transaction_date')}"
        if trade_id not in seen and not is_tax_payment(trade):
            if send_telegram(format_congressional_message(trade, source)):
                new_seen.add(trade_id)
                sent_count += 1
                time.sleep(1)
    
    # Form 3/4/5
    print("\n📋 Insider Trading...")
    for form_type in ['3', '4', '5']:
        for filing in check_sec_filings(form_type, days_back=3 if form_type != '4' else 2):
            filing_id = f"form{form_type}_{filing['link']}"
            if filing_id not in seen:
                if send_telegram(format_insider_form4_message(filing)):
                    new_seen.add(filing_id)
                    sent_count += 1
                    time.sleep(1)
    
    # Form 13D/G
    print("\n📊 13D/G...")
    for form_type in ['SC13D', 'SC13G', 'SC13G/A']:
        for filing in check_sec_filings(form_type, days_back=5, count=40):
            filing_id = f"{form_type}_{filing['link']}"
            if filing_id not in seen:
                if send_telegram(format_form13dg_message(filing)):
                    new_seen.add(filing_id)
                    sent_count += 1
                    time.sleep(1)
    
    # Form 13F (CON PARSING COMPLETO)
    print("\n💼 13F (Full Parsing)...")
    filings = check_sec_filings('13F-HR', days_back=7, count=200)
    
    for filing in filings:
        filing_id = f"13f_{filing['link']}"
        
        if filing_id in seen:
            continue
        
        # Solo investitori famosi
        if not is_notable_investor(filing['title']):
            new_seen.add(filing_id)
            continue
        
        fund_name = extract_company_from_title(filing['title'])
        
        print(f"   Parsing {fund_name}...")
        
        # Scarica e parsa 13F corrente
        current_holdings = parse_13f_xml(filing['link'])
        
        if not current_holdings:
            print(f"   Failed to parse, sending simple alert")
            # Fallback: invia notifica semplice
            msg = f"""⭐️ <b>13F - HOLDINGS TRIMESTRALE</b>

👤 Fondo: <b>{fund_name}</b>
📅 Data: {filing['date']}

🔗 <a href="{filing['link']}">Vedi tutte le posizioni</a>"""
            send_telegram(msg)
            new_seen.add(filing_id)
            sent_count += 1
            time.sleep(1)
            continue
        
        # Calcola valore totale
        total_value = sum(h['value'] for h in current_holdings.values())
        
        # Cerca 13F precedente in cache
        previous_holdings = cache_13f.get(fund_name, {})
        
        # Confronta
        changes = compare_13f_holdings(current_holdings, previous_holdings)
        
        # Invia notifica dettagliata
        msg = format_13f_detailed_message(fund_name, changes, total_value)
        
        if send_telegram(msg):
            new_seen.add(filing_id)
            sent_count += 1
            print(f"   ✅ Sent detailed 13F for {fund_name}")
            
            # Salva in cache per il prossimo trimestre
            cache_13f[fund_name] = current_holdings
            save_json_file(CACHE_13F_FILE, cache_13f)
            
            time.sleep(2)  # Pausa più lunga per messaggi lunghi
    
    save_seen(new_seen)
    print(f"\n{'='*60}")
    print(f"✅ Sent {sent_count} alerts")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
