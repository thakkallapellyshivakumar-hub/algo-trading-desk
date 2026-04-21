import upstox_client
import sys
import os
import time
import pandas as pd
import requests
from datetime import datetime

# ==========================================
# 1. TELEGRAM SETTINGS
# ==========================================
ENABLE_TELEGRAM = True  
TELEGRAM_TOKEN = "**********"      # 🔥 Put your real token here
TELEGRAM_CHAT_ID = "**********"    # 🔥 Put your real Chat ID here

# ==========================================
# 2. SCANNER PARAMETERS
# ==========================================
MIN_PRICE = 200.0  
S1_BODY_PCT = 0.60
S1_VOL_MULT = 2.0
S1_RSI_BULL_MIN = 50
S1_RSI_BEAR_MAX = 40
S1_NARROW_MAX_PCT = 3.0

S2_RSI_BULL_MIN = 60
S2_RSI_BEAR_MAX = 40
S2_BODY_PCT = 0.65
S2_VOL_MULT = 2.0

# ==========================================
# 3. GLOBAL MEMORY & DYNAMIC F&O BUILDER
# ==========================================
try:
    token = open("access_token.txt").read().strip()
except:
    token = "MOCK_TOKEN"

scanner_results = [] 
live_5m_candles = {}

def build_fno_basket():
    print("📥 Downloading latest Upstox Instrument Master (Takes ~5 seconds)...")
    try:
        url = 'https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz'
        df = pd.read_csv(url)

        IGNORE_STOCKS = [
            "IDEA", "YESBANK", "SUZLON", "IDFCFIRSTB", "NHPC", "NMDC", "NBCC", 
            "GMRAIRPORT", "INOXWIND", "IRFC", "PNB", "VMM", "MOTHERSON", "IEX", 
            "IREDA", "CANBK", "IOC", "BANKINDIA", "PPLPHARMA", "SAMMAANCAP", 
            "GAIL", "SAIL", "BANDHANBNK", "ASHOKLEY", "UNIONBANK", "HUDCO", "ADANIPOWER"
        ]

        fno_symbols = df[(df['exchange'] == 'NSE_FO') & (df['instrument_type'] == 'FUTSTK')]['name'].dropna().unique()
        eq_df = df[(df['exchange'] == 'NSE_EQ') & (df['name'].isin(fno_symbols)) & (~df['name'].isin(IGNORE_STOCKS))]

        sector_map = {
            "HDFCBANK": "NIFTY_BANK", "ICICIBANK": "NIFTY_BANK", "SBIN": "NIFTY_BANK", "KOTAKBANK": "NIFTY_BANK", "AXISBANK": "NIFTY_BANK",
            "TCS": "NIFTY_IT", "INFY": "NIFTY_IT", "HCLTECH": "NIFTY_IT", "WIPRO": "NIFTY_IT", "TECHM": "NIFTY_IT",
            "RELIANCE": "NIFTY_ENERGY", "ONGC": "NIFTY_ENERGY", "NTPC": "NIFTY_ENERGY",
            "TATAMOTORS": "NIFTY_AUTO", "M&M": "NIFTY_AUTO", "MARUTI": "NIFTY_AUTO"
        }

        dynamic_basket = {}
        for index, row in eq_df.iterrows():
            key = row['instrument_key']
            name = row['name']
            sector = "GENERAL_FNO"
            for mapped_name, mapped_sector in sector_map.items():
                if mapped_name in str(name):
                    sector = mapped_sector
                    break
            dynamic_basket[key] = {"name": name, "sector": sector}
            
        print(f"✅ Successfully loaded {len(dynamic_basket)} Premium F&O Stocks (Ignored {len(IGNORE_STOCKS)} cheap stocks)!")
        return dynamic_basket
    except Exception as e:
        print(f"❌ Error downloading F&O list: {e}")
        sys.exit()

FNO_BASKET = build_fno_basket()

# ==========================================
# 4. TELEGRAM FUNCTION
# ==========================================
def send_telegram_alert(message):
    if not ENABLE_TELEGRAM or "PASTE_YOUR" in TELEGRAM_TOKEN or "******" in TELEGRAM_TOKEN: 
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"⚠️ Telegram Error: {e}")

# ==========================================
# 5. SCANNER LOGIC & CONFLUENCE ENGINE
# ==========================================
def evaluate_stock(stock_key, candle_open, candle_high, candle_low, candle_close, candle_vol):
    stock_info = FNO_BASKET.get(stock_key, {"name": stock_key, "sector": "UNKNOWN"})
    stock_name = stock_info["name"]
    sector_name = stock_info["sector"]
    
    candle_range = candle_high - candle_low
    if candle_range == 0: return
    
    if candle_close < MIN_PRICE:
        return 
    
    # Mock pre-market & live index data
    pm = {
        "rsi": 56, "pdh": candle_high * 0.99, "pdl": candle_low * 1.01, 
        "avg_vol_20d": 1000, "3d_range_pct": 2.5, "15m_high": candle_high * 0.98,
        "15m_low": candle_low * 1.02, "gap_up": True, "gap_down": False,
        "nifty_is_bullish": True,
        "sector_is_bullish": True if sector_name != "NIFTY_BANK" else False
    }
        
    body = abs(candle_close - candle_open)
    body_pct = body / candle_range
    is_green = candle_close > candle_open
    is_red = candle_close < candle_open
    
    signal_name = None
    trade_dir = None

    # SCANNER 1: Breakouts
    if pm["3d_range_pct"] <= S1_NARROW_MAX_PCT and candle_vol >= (pm["avg_vol_20d"] * S1_VOL_MULT):
        if is_green and body_pct >= S1_BODY_PCT and candle_close > pm["pdh"] and pm["rsi"] >= S1_RSI_BULL_MIN:
            signal_name = "Bullish Breakout"; trade_dir = "BULL"
        elif is_red and body_pct >= S1_BODY_PCT and candle_close < pm["pdl"] and pm["rsi"] <= S1_RSI_BEAR_MAX:
            signal_name = "Bearish Breakdown"; trade_dir = "BEAR"

    # SCANNER 2: Trenders
    if candle_vol >= (pm["avg_vol_20d"] * S2_VOL_MULT) and body_pct >= S2_BODY_PCT and signal_name is None:
        if pm["gap_up"] and is_green and candle_close > pm["15m_high"] and pm["rsi"] >= S2_RSI_BULL_MIN:
            signal_name = "Bullish Day Trender"; trade_dir = "BULL"
        elif pm["gap_down"] and is_red and candle_close < pm["15m_low"] and pm["rsi"] <= S2_RSI_BEAR_MAX:
            signal_name = "Bearish Day Trender"; trade_dir = "BEAR"

    # CONFLUENCE CHECK
    if signal_name:
        is_high_prob = False
        if trade_dir == "BULL" and pm["nifty_is_bullish"] and pm["sector_is_bullish"]: is_high_prob = True
        elif trade_dir == "BEAR" and not pm["nifty_is_bullish"] and not pm["sector_is_bullish"]: is_high_prob = True

        prob_tag = "💎 HIGH PROBABILITY" if is_high_prob else "⚠️ COUNTER-TREND"
        dir_icon = "🟢" if trade_dir == "BULL" else "🔴"
        
        alert_msg = (
            f"{dir_icon} <b>{stock_name}</b> | {signal_name}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price: {candle_close}\n"
            f"📈 RSI: {pm['rsi']}\n"
            f"🎯 Setup: {prob_tag}\n"
            f"📊 Sector ({sector_name}): {'Positive' if pm['sector_is_bullish'] else 'Negative'}"
        )
        
        print(f"\n{alert_msg.replace('<b>', '').replace('</b>', '')}") 
        send_telegram_alert(alert_msg) 
        
        scanner_results.append({
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Stock": stock_name,
            "Signal": signal_name, "Price": candle_close, "Quality": prob_tag
        })

# ==========================================
# 6. WEBSOCKET HANDLER (BUILDS 5M CANDLES)
# ==========================================
last_processed_5m = datetime.now().minute // 5

def on_message(message):
    global last_processed_5m, live_5m_candles
    try:
        feeds = message.get("feeds", {})
        now = datetime.now()
        current_5m_block = now.minute // 5
        
        if current_5m_block != last_processed_5m:
            for stock_key, c in live_5m_candles.items():
                # Pass the true calculated volume to the evaluator
                evaluate_stock(stock_key, c['open'], c['high'], c['low'], c['close'], c['vol'])
            live_5m_candles.clear() 
            last_processed_5m = current_5m_block

        for key, data in feeds.items():
            if "marketFF" in data.get("fullFeed", {}):
                mff = data["fullFeed"]["marketFF"]
                ltp = mff.get("ltpc", {}).get("ltp", 0)
                vtt = mff.get("vtt", 0) # 🔥 TRUTH: Actual Total Volume Traded Today
                
                if ltp > 0:
                    if key not in live_5m_candles:
                        # 🔥 Record the exact volume at the moment the 5m candle is born
                        live_5m_candles[key] = {'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp, 'start_vtt': vtt, 'vol': 0}
                    
                    c = live_5m_candles[key]
                    c['high'] = max(c['high'], ltp); c['low'] = min(c['low'], ltp)
                    c['close'] = ltp
                    
                    # 🔥 The True 5M Volume = Current Total Volume - Starting Volume
                    if vtt > 0 and c['start_vtt'] > 0:
                        c['vol'] = vtt - c['start_vtt']
                        
    except Exception: pass

# ==========================================
# 7. EXCEL EXPORT
# ==========================================
def save_to_excel():
    if len(scanner_results) > 0:
        df = pd.DataFrame(scanner_results)
        filename = f"Scanner_Results_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        df.to_excel(filename, index=False)
        print(f"\n📁 Saved {len(scanner_results)} alerts to {filename}")
    else:
        print("\nℹ️ No alerts triggered today. Excel file not created.")

# ==========================================
# 8. EXECUTION
# ==========================================
if __name__ == "__main__":
    
    SIMULATE_TEST = False 
    
    if SIMULATE_TEST:
        print("\n🛠️ RUNNING WEEKEND TEST (Testing Dynamic List & Telegram)...")
        test_keys = list(FNO_BASKET.keys())
        if len(test_keys) >= 2:
            evaluate_stock(test_keys[0], candle_open=4000, candle_high=4050, candle_low=3990, candle_close=4045, candle_vol=5000)
            evaluate_stock(test_keys[1], candle_open=1500, candle_high=1530, candle_low=1490, candle_close=1525, candle_vol=3000)
        
        save_to_excel()
        os._exit(0)

    # --- LIVE WEBSOCKET ---
    conf = upstox_client.Configuration(); conf.access_token = token
    streamer = upstox_client.MarketDataStreamerV3(upstox_client.ApiClient(conf), list(FNO_BASKET.keys()), "full")
    streamer.on("open", lambda: print(f"🔭 SCANNER ONLINE | Watching {len(FNO_BASKET)} Premium F&O Stocks... (Press Ctrl+C to stop)"))
    streamer.on("message", on_message) 
    streamer.connect()
    
    try:
        while True: 
            t = datetime.now()
            if t.hour == 15 and t.minute >= 31:
                print("\n🏁 Market Closed. Generating Final Excel Report & Shutting Down...")
                save_to_excel()
                try: streamer.disconnect()
                except: pass
                os._exit(0) 
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Manual Stop Triggered! Generating Final Excel Report...")
        save_to_excel()
        os._exit(0)