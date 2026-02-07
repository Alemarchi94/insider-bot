import requests
import json
import os
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import time

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['CHAT_ID']
SEEN_FILE = 'seen_transactions.json'

# User-Agent obbligatorio per SEC
HEADERS = {
    'User-Agent': 'Alessandro Marchi alessadro94marchi@gmail.com',  
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

# Fondi/investitori famosi da monitorare
NOTABLE_INVESTORS = [
    'berkshire hathaway',
    'warren buffett',
    'scion',
    'michael burry',
    'burry',
    'bill ackman',
    'pershing square',
    'carl icahn',
    'icahn enterprises',
    'bridgewater',
    'ray dalio',
    'renaissance technologies',
    'citadel',
    'ken griffin',
    'tiger global',
    'coatue',
    'greenlight',
    'david einhorn',
    'baupost',
    'seth klarman',
    'third point',
    'dan loeb',
    'elliott management',
    'paul singer',
    'appaloosa',
    'david tepper',
    'lone pine',
    'viking global',
    'millennium',
    'point72',
    'steve cohen',
    'two sigma',
    'de shaw',
    'aqr',
    'paulson',
    'john paulson',
    'soros',
    'george soros',
    'stanley druckenmiller',
    'duquesne',
    'bill miller',
    'bill gates',
    'cascade investment',
    'jeff bezos',
    'mark zuckerberg',
    'elon musk',
    'larry ellison',
    'jim simons',
    'chase coleman',
    'tiger cub',
    'sequoia',
    'a16z',
    'andreessen horowitz'
]

def load_seen():
    try:
        with open(SEEN_FILE, 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, 'w') as f:
        json.dump(list(seen), f)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            'chat_id': CHAT_ID,
            'text': message[:4096],
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        })
        return True
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def check_congressional_trades():
    """House Stock Watcher"""
    url = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
    
    try:
        response = requests.get(url, timeout=10)
        trades = response.json()
        
        recent = []
        cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        for trade in trades:
            if trade.get('disclosure_date', '') >= cutoff:
                recent.append(trade)
        
        return recent
    except Exception as e:
        print(f"Congressional error: {e}")
        return []

def check_senate_trades():
    """Senate stock disclosure"""
    url = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"
    
    try:
        response = requests.get(url, timeout=10)
        trades = response.json()
        
        recent = []
        cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        for trade in trades:
            if trade.get('disclosure_date', '') >= cutoff:
                recent.append(trade)
        
        return recent
    except Exception as e:
        print(f"Senate error: {e}")
        return []

def check_sec_filings(form_type, days_back=2, count=100):
    """
    Funzione generica per controllare filing SEC
    form_type: '3', '4', '5', 'SC13D', 'SC13G', 'SC13G/A', '13F-HR', ecc.
    """
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
            
            time.sleep(0.15)  # Rate limit: 10 req/sec
            
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)
            
            if response.status_code != 200:
                print(f"SEC error for {form_type}: {response.status_code}")
                continue
            
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            
            for entry in root.findall('atom:entry', ns):
                try:
                    title = entry.find('atom:title', ns).text
                    link = entry.find('atom:link', ns).attrib['href']
                    updated = entry.find('atom:updated', ns).text
                    
                    filings.append({
                        'title': title,
                        'link': link,
                        'date': updated[:10],
                        'type': form_type
                    })
                except Exception as e:
                    print(f"Parse error: {e}")
                    continue
        
        return filings
    
    except Exception as e:
        print(f"Form {form_type} error: {e}")
        return []

def check_form3():
    """Form 3 - Nuovi insider (initial ownership)"""
    return check_sec_filings('3', days_back=3, count=50)

def check_form4():
    """Form 4 - Insider transactions"""
    return check_sec_filings('4', days_back=2, count=100)

def check_form5():
    """Form 5 - Annual insider transactions"""
    return check_sec_filings('5', days_back=3, count=30)

def check_form13d():
    """Form 13D - Acquisizioni attiviste >5%"""
    return check_sec_filings('SC13D', days_back=5, count=40)

def check_form13g():
    """Form 13G - Acquisizioni passive >5%"""
    filings = []
    filings.extend(check_sec_filings('SC13G', days_back=5, count=40))
    filings.extend(check_sec_filings('SC13G/A', days_back=5, count=60))  # Amendments (modifiche anche sotto 5%)
    return filings

def check_form13f():
    """
    Form 13F-HR - Holdings trimestrali fondi >$100M
    Questi escono ogni trimestre (45 giorni dopo fine trimestre)
    """
    return check_sec_filings('13F-HR', days_back=7, count=200)

def is_notable_investor(title):
    """Identifica investitori famosi"""
    title_lower = title.lower()
    return any(name in title_lower for name in NOTABLE_INVESTORS)

def is_tax_payment(trade):
    """Filtra pagamenti tasse"""
    comment = str(trade.get('comment', '')).lower()
    type_tx = str(trade.get('type', '')).lower()
    
    tax_keywords = ['tax', 'withholding', 'tax obligation', 'tax liability', 'tax withholding']
    return any(keyword in comment for keyword in tax_keywords)

def format_congressional_message(trade, source):
    """Formatta messaggio per trade congressional"""
    owner = trade.get('representative', trade.get('senator', 'N/A'))
    ticker = trade.get('ticker', 'N/A')
    amount = trade.get('amount', 'N/A')
    tx_type = trade.get('type', 'N/A')
    date = trade.get('transaction_date', trade.get('disclosure_date', 'N/A'))
    
    vips = ['pelosi', 'trump', 'mcconnell', 'schumer', 'biden', 'warren', 'cruz', 'ocasio-cortez', 'aoc']
    is_vip = any(vip in owner.lower() for vip in vips)
    
    prefix = "🔥🔥 <b>VIP POLITICO</b> 🔥🔥" if is_vip else "🏛 <b>CONGRESSO</b>"
    
    return f"""{prefix}

👤 <b>{owner}</b>
📊 Ticker: <b>{ticker}</b>
💰 Importo: {amount}
📈 Tipo: {tx_type}
📅 Data transazione: {date}
🏢 Camera: {source}

{trade.get('comment', '')}"""

def format_sec_message(filing):
    """Formatta messaggio per filing SEC"""
    title = filing['title']
    form_type = filing['type']
    link = filing['link']
    date = filing['date']
    
    is_notable = is_notable_investor(title)
    
    # Emoji e prefix basati sul tipo
    if form_type == '3':
        emoji = "🆕"
        desc = "NUOVO INSIDER"
    elif form_type == '4':
        emoji = "📋"
        desc = "INSIDER TRADING"
    elif form_type == '5':
        emoji = "📅"
        desc = "INSIDER ANNUAL"
    elif form_type in ['SC13D']:
        emoji = "🚨"
        desc = "ACQUISIZIONE ATTIVISTA (&gt;5%)"
    elif form_type in ['SC13G', 'SC13G/A']:
        emoji = "📊"
        desc = "13G - ACQUISIZIONE/MODIFICA"
    elif form_type == '13F-HR':
        emoji = "💼"
        desc = "13F - HOLDINGS TRIMESTRALE"
    else:
        emoji = "📄"
        desc = "SEC FILING"
    
    # Evidenzia investitori famosi
    if is_notable:
        prefix = f"⭐️⭐️ <b>INVESTITORE FAMOSO</b> ⭐️⭐️\n{emoji} <b>{desc}</b>"
    else:
        prefix = f"{emoji} <b>{desc}</b>"
    
    return f"""{prefix}

📄 {title}
📅 Data filing: {date}
🔗 <a href="{link}">Vedi filing SEC completo</a>"""

def main():
    seen = load_seen()
    new_seen = seen.copy()
    sent_count = 0
    
    print(f"\n{'='*60}")
    print(f"🤖 INSIDER BOT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # ========== 1. CONGRESSIONAL TRADES ==========
    print("📊 Checking Congressional trades...")
    house_trades = check_congressional_trades()
    senate_trades = check_senate_trades()
    
    print(f"   Found {len(house_trades)} House + {len(senate_trades)} Senate trades")
    
    for trade in house_trades:
        trade_id = f"house_{trade.get('representative')}_{trade.get('ticker')}_{trade.get('transaction_date')}"
        
        if trade_id in seen:
            continue
            
        if is_tax_payment(trade):
            print(f"   ⏭ Skipped (tax): {trade_id}")
            continue
        
        try:
            message = format_congressional_message(trade, 'House of Representatives')
            if send_telegram(message):
                new_seen.add(trade_id)
                sent_count += 1
                print(f"   ✅ Sent: {trade.get('representative')} - {trade.get('ticker')}")
                time.sleep(1)
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    for trade in senate_trades:
        trade_id = f"senate_{trade.get('senator')}_{trade.get('ticker')}_{trade.get('transaction_date')}"
        
        if trade_id in seen:
            continue
            
        if is_tax_payment(trade):
            print(f"   ⏭ Skipped (tax): {trade_id}")
            continue
        
        try:
            message = format_congressional_message(trade, 'Senate')
            if send_telegram(message):
                new_seen.add(trade_id)
                sent_count += 1
                print(f"   ✅ Sent: {trade.get('senator')} - {trade.get('ticker')}")
                time.sleep(1)
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # ========== 2. FORM 3 (New Insiders) ==========
    print("\n🆕 Checking Form 3 (New Insiders)...")
    form3_filings = check_form3()
    print(f"   Found {len(form3_filings)} Form 3 filings")
    
    for filing in form3_filings:
        filing_id = f"form3_{filing['link']}"
        
        if filing_id in seen:
            continue
        
        try:
            message = format_sec_message(filing)
            if send_telegram(message):
                new_seen.add(filing_id)
                sent_count += 1
                print(f"   ✅ Sent: {filing['title'][:60]}")
                time.sleep(1)
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # ========== 3. FORM 4 (Insider Trading) ==========
    print("\n📋 Checking Form 4 (Insider Transactions)...")
    form4_filings = check_form4()
    print(f"   Found {len(form4_filings)} Form 4 filings")
    
    for filing in form4_filings:
        filing_id = f"form4_{filing['link']}"
        
        if filing_id in seen:
            continue
        
        try:
            message = format_sec_message(filing)
            if send_telegram(message):
                new_seen.add(filing_id)
                sent_count += 1
                print(f"   ✅ Sent: {filing['title'][:60]}")
                time.sleep(1)
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # ========== 4. FORM 5 (Annual Insider) ==========
    print("\n📅 Checking Form 5 (Annual Insider)...")
    form5_filings = check_form5()
    print(f"   Found {len(form5_filings)} Form 5 filings")
    
    for filing in form5_filings:
        filing_id = f"form5_{filing['link']}"
        
        if filing_id in seen:
            continue
        
        try:
            message = format_sec_message(filing)
            if send_telegram(message):
                new_seen.add(filing_id)
                sent_count += 1
                print(f"   ✅ Sent: {filing['title'][:60]}")
                time.sleep(1)
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # ========== 5. FORM 13D (Activist >5%) ==========
    print("\n🚨 Checking Form 13D (Activist Acquisitions)...")
    form13d_filings = check_form13d()
    print(f"   Found {len(form13d_filings)} Form 13D filings")
    
    for filing in form13d_filings:
        filing_id = f"form13d_{filing['link']}"
        
        if filing_id in seen:
            continue
        
        try:
            message = format_sec_message(filing)
            if send_telegram(message):
                new_seen.add(filing_id)
                sent_count += 1
                notable = "⭐️ NOTABLE" if is_notable_investor(filing['title']) else ""
                print(f"   ✅ Sent {notable}: {filing['title'][:60]}")
                time.sleep(1)
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # ========== 6. FORM 13G/13G/A (Passive acquisitions + amendments) ==========
    print("\n📊 Checking Form 13G/A (Passive Acquisitions & Changes)...")
    form13g_filings = check_form13g()
    print(f"   Found {len(form13g_filings)} Form 13G/A filings")
    
    for filing in form13g_filings:
        filing_id = f"form13g_{filing['link']}"
        
        if filing_id in seen:
            continue
        
        # Priorità agli investitori famosi
        is_notable = is_notable_investor(filing['title'])
        
        try:
            message = format_sec_message(filing)
            if send_telegram(message):
                new_seen.add(filing_id)
                sent_count += 1
                notable = "⭐️ NOTABLE" if is_notable else ""
                print(f"   ✅ Sent {notable}: {filing['title'][:60]}")
                time.sleep(1)
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # ========== 7. FORM 13F-HR (Quarterly Holdings) ==========
    print("\n💼 Checking Form 13F-HR (Quarterly Fund Holdings)...")
    form13f_filings = check_form13f()
    print(f"   Found {len(form13f_filings)} Form 13F filings")
    
    for filing in form13f_filings:
        filing_id = f"form13f_{filing['link']}"
        
        if filing_id in seen:
            continue
        
        # Solo investitori famosi per 13F (altrimenti troppo spam)
        if is_notable_investor(filing['title']):
            try:
                message = format_sec_message(filing)
                if send_telegram(message):
                    new_seen.add(filing_id)
                    sent_count += 1
                    print(f"   ✅ Sent ⭐️: {filing['title'][:60]}")
                    time.sleep(1)
            except Exception as e:
                print(f"   ❌ Error: {e}")
        else:
            # Marca come visto ma non inviare (troppo spam)
            new_seen.add(filing_id)
    
    # ========== SALVA E SUMMARY ==========
    save_seen(new_seen)
    
    print(f"\n{'='*60}")
    print(f"✅ COMPLETATO")
    print(f"   Nuovi alert inviati: {sent_count}")
    print(f"   Totale tracking: {len(new_seen)} transazioni")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
