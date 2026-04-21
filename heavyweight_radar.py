import upstox_client
import sys
import os
import time
import pandas as pd
from datetime import datetime

# ==========================================
# 1. THE HEAVYWEIGHT BASKET (47% of Nifty Weight)
# ==========================================
RADAR_WEIGHTS = {
    "HDFCBANK": 11.0,
    "RELIANCE": 10.0,
    "ICICIBANK": 8.0,
    "INFY": 6.0,
    "LT": 4.0,
    "TCS": 4.0,
    "ITC": 4.0
}

INDICES = {
    "NSE_INDEX|Nifty 50": "NIFTY 50",
    "NSE_INDEX|Nifty Bank": "NIFTY BANK",
    "NSE_INDEX|Nifty IT": "NIFTY IT"
}

try:
    token = open("access_token.txt").read().strip()
except FileNotFoundError:
    print("❌ ERROR: access_token.txt not found. Run auth.py first!")
    sys.exit()

radar_keys = {}
live_data = {}
last_print_time = time.time()

# ==========================================
# 2. FETCH KEYS & BUILD RADAR
# ==========================================
def setup_radar():
    print("📥 Loading Heavyweight Blueprint...")
    try:
        url = 'https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz'
        df = pd.read_csv(url)
        
        eq_df = df[(df['exchange'] == 'NSE_EQ') & (df['name'].isin(RADAR_WEIGHTS.keys()))]
        
        for _, row in eq_df.iterrows():
            radar_keys[row['instrument_key']] = row['name']
            live_data[row['name']] = {'ltp': 0.0, 'cp': 0.0, 'weight': RADAR_WEIGHTS[row['name']]}
            
        for key, name in INDICES.items():
            radar_keys[key] = name
            live_data[name] = {'ltp': 0.0, 'cp': 0.0, 'weight': 0}
            
        print(f"✅ Radar Locked onto Top {len(RADAR_WEIGHTS)} Heavyweights and {len(INDICES)} Indices!")
        return list(radar_keys.keys())
    except Exception as e:
        print(f"❌ Blueprint Error: {e}")
        sys.exit()

# ==========================================
# 3. LIVE DASHBOARD RENDERER
# ==========================================
def print_dashboard():
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("="*50)
    print(f" 🦅 INSTITUTIONAL RADAR | Live as of {datetime.now().strftime('%H:%M:%S')}")
    print("="*50)
    
    score = 0.0
    
    print(" 🏢 TOP 7 HEAVYWEIGHTS (47% OF NIFTY):")
    for name, data in live_data.items():
        if data['weight'] > 0 and data['cp'] > 0:
            pct_change = ((data['ltp'] - data['cp']) / data['cp']) * 100
            score += (pct_change * data['weight'])
            color_icon = "🟢" if pct_change >= 0 else "🔴"
            print(f"  {color_icon} {name:<10}: ₹{data['ltp']:<8.2f} ({pct_change:>+5.2f}%)")
            
    normalized_score = score / 5.0 
    
    print("-" * 50)
    
    print(" 📊 MAJOR SECTORS:")
    for name, data in live_data.items():
        if data['weight'] == 0 and data['cp'] > 0:
            pct_change = ((data['ltp'] - data['cp']) / data['cp']) * 100
            color_icon = "🟢" if pct_change >= 0 else "🔴"
            print(f"  {color_icon} {name:<10}: {data['ltp']:<8.2f} ({pct_change:>+5.2f}%)")

    print("="*50)
    
    score_tag = "NEUTRAL"
    if normalized_score >= 3.0: score_tag = "🚀 EXTREME BULLISH (Trap for Puts)"
    elif normalized_score > 1.0: score_tag = "📈 BULLISH"
    elif normalized_score <= -3.0: score_tag = "🩸 EXTREME BEARISH (Trap for Calls)"
    elif normalized_score < -1.0: score_tag = "📉 BEARISH"
    
    print(f" 🧠 INTERNAL STRENGTH SCORE: {normalized_score:>+5.2f}  [{score_tag}]")
    print("="*50)
    print(" Press Ctrl+C to stop.")

# ==========================================
# 4. WEBSOCKET HANDLER
# ==========================================
def on_message(message):
    global last_print_time
    try:
        feeds = message.get("feeds", {})
        
        for key, data in feeds.items():
            name = radar_keys.get(key)
            if not name: continue
            
            ff = data.get("fullFeed", {})
            
            if "marketFF" in ff:
                ltp = ff["marketFF"].get("ltpc", {}).get("ltp", 0)
                cp = ff["marketFF"].get("ltpc", {}).get("cp", 0) 
                if ltp > 0: live_data[name]['ltp'] = ltp
                if cp > 0: live_data[name]['cp'] = cp
            
            elif "indexFF" in ff:
                ltp = ff["indexFF"].get("ltpc", {}).get("ltp", 0)
                cp = ff["indexFF"].get("ltpc", {}).get("cp", 0)
                if ltp > 0: live_data[name]['ltp'] = ltp
                if cp > 0: live_data[name]['cp'] = cp
                
        if time.time() - last_print_time >= 1.0:
            print_dashboard()
            last_print_time = time.time()
            
    except Exception: pass

# ==========================================
# 5. EXECUTION
# ==========================================
if __name__ == "__main__":
    subscription_keys = setup_radar()
    
    conf = upstox_client.Configuration(); conf.access_token = token
    streamer = upstox_client.MarketDataStreamerV3(upstox_client.ApiClient(conf), subscription_keys, "full")
    streamer.on("message", on_message)
    streamer.connect()
    
    # 🔥 PERFECTED ENGINE ROOM: Only one loop for checking time and handling exit
    try:
        while True:
            t = datetime.now()
            # 🔥 Auto-Shutdown at 3:31 PM
            if t.hour == 15 and t.minute >= 31:
                os.system('cls' if os.name == 'nt' else 'clear')
                print("\n🏁 Market Closed. Radar Offline.")
                os._exit(0)
            time.sleep(1)
    except KeyboardInterrupt:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n🛑 Radar Offline.")
        os._exit(0)