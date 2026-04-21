import upstox_client
import sys
import os
import time
import pyodbc
import requests
import pandas as pd
from datetime import datetime, time as dt_time

# ==============================
# 1. STRATEGY PARAMETERS (V2.3 - Ultimate Risk Engine)
# ==============================
TREND_THRESHOLD = 20.0        
PCR_BULLISH = 1.0             
PCR_BEARISH = 0.8             
TARGET_PTS = 30.0             
SL_PTS = 15.0                 

# 🔥 NEW: Precision Time Filters
TRADE_START_TIME = dt_time(9, 18, 0) 
TRADE_STOP_NORMAL = dt_time(14, 55, 0)   # Stop fresh trades at 2:55 PM normally
TRADE_STOP_EXPIRY = dt_time(14, 45, 0)   # Stop fresh trades at 2:45 PM on expiry
NIFTY_EXPIRY_DAY = 1                     # 🔥 UPDATED: 1 = Tuesday (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri)

# Position Sizing Parameters
LOT_SIZE = 65       
NUMBER_OF_LOTS = 1  
QUANTITY = LOT_SIZE * NUMBER_OF_LOTS

# ==============================
# 2. GLOBAL SYSTEM STATE
# ==============================
conn_str = ("DRIVER={ODBC Driver 17 for SQL Server};" r"SERVER=localhost\SQLEXPRESS;" "DATABASE=master;" "Trusted_Connection=yes;")
conn = pyodbc.connect(conn_str, autocommit=True)
cursor = conn.cursor()

# AUTO-SQL REPAIR
try:
    cursor.execute("ALTER TABLE Mock_Trades ADD quantity INT DEFAULT 65;")
    print("✅ System Auto-Repaired: Added missing 'quantity' column to database.")
except Exception:
    pass 

try:
    token = open("access_token.txt").read().strip()
except FileNotFoundError:
    print("❌ ERROR: access_token.txt not found. Run auth.py first!")
    sys.exit()

instrument_map = {}
tick_buffer = []  
oi_data = {"CE": 0, "PE": 0} 
live_prices = {} 
active_trade = None
last_processed_minute = datetime.now().minute
prev_nifty_close = 0

ce_key_global = ""
pe_key_global = ""

# ==============================
# 3. DYNAMIC KEY FETCHER
# ==============================
def get_live_keys(access_token):
    global ce_key_global, pe_key_global
    print("🔍 Syncing ATM Option Chain & Greeks...")
    url = "https://api.upstox.com/v2/instruments/search"
    headers = {'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'}
    
    res_ce = requests.get(url, headers=headers, params={'query': 'NIFTY', 'segments': 'FO', 'instrument_types': 'CE', 'expiry': 'current_week', 'atm_offset': 0})
    ce_data = res_ce.json()['data'][0]
    
    res_pe = requests.get(url, headers=headers, params={'query': 'NIFTY', 'segments': 'FO', 'instrument_types': 'PE', 'expiry': 'current_week', 'atm_offset': 0})
    pe_data = res_pe.json()['data'][0]
    
    ce_key_global = ce_data['instrument_key']
    pe_key_global = pe_data['instrument_key']
    
    instrument_map[ce_key_global] = ce_data['trading_symbol']
    instrument_map[pe_key_global] = pe_data['trading_symbol']
    
    print(f"✅ Targets Locked: {ce_data['trading_symbol']} | {pe_data['trading_symbol']}\n")
    return ce_key_global, pe_key_global

# ==============================
# 4. DEMO EXECUTION ENGINE
# ==============================
def execute_mock_trade(instrument, price, side):
    global active_trade
    if active_trade: return
    if price > 5000: return 

    print(f"\n🚀 EXECUTION: Entering {side} @ ₹{price} | Qty: {QUANTITY} | {instrument}")
    
    # 🔥 TSL UPGRADE: Added 'tsl_active' memory switch
    active_trade = {"instrument": instrument, "entry_price": price, "side": side, "qty": QUANTITY, "tsl_active": False}

    try:
        cursor.execute("""
            INSERT INTO Mock_Trades (instrument, side, entry_price, status, quantity) 
            VALUES (?, ?, ?, 'OPEN', ?)
        """, (instrument, side, price, QUANTITY))
    except Exception as e:
        print(f"⚠️ SQL Database Error during Entry: {e}")

def monitor_trade(current_price):
    global active_trade
    if not active_trade: return
    
    pnl_points = current_price - active_trade['entry_price'] if active_trade['side'] == 'BUY' else active_trade['entry_price'] - current_price
    
    # 🔥 THE TRAILING STOP LOSS MEMORY PROTOCOL
    if pnl_points >= 10.0 and not active_trade['tsl_active']:
        active_trade['tsl_active'] = True
        print(f"\n🛡️ TSL ACTIVATED! Locked in breakeven for {active_trade['instrument']} (+10 pts reached)")
        
    current_sl = 0.0 if active_trade['tsl_active'] else -SL_PTS
    
    if pnl_points >= TARGET_PTS or pnl_points <= current_sl:
        rupee_pnl = pnl_points * active_trade['qty']
        
        if pnl_points >= TARGET_PTS:
            status_msg = f"🎯 TARGET HIT (+{TARGET_PTS} pts)"
        elif current_sl == 0.0 and pnl_points <= 0.0:
            status_msg = f"🛡️ BREAKEVEN TSL HIT (Capital Protected)"
        else:
            status_msg = f"🛑 STOP LOSS (-{SL_PTS} pts)"
            
        print(f"\n{status_msg}: Closing @ ₹{current_price} | Realized P&L: ₹{round(rupee_pnl, 2)}")
        
        try:
            cursor.execute("""
                UPDATE Mock_Trades 
                SET exit_time = GETDATE(), exit_price = ?, pnl = ?, status = 'CLOSED' 
                WHERE status = 'OPEN'
            """, (current_price, rupee_pnl))
        except Exception as e:
            print(f"⚠️ SQL Database Error during Exit: {e}")
            
        active_trade = None

# ==============================
# 5. DATA ENGINE & TREND DETECTION
# ==============================
def save_candles(df_minute, timeframe, table):
    if df_minute.empty: return
    try:
        ohlc = df_minute.groupby('instrument')['ltp'].ohlc()
        for inst, d in ohlc.iterrows():
            cursor.execute(f"INSERT INTO {table} (candle_time, instrument, [open], [high], [low], [close]) VALUES (?, ?, ?, ?, ?, ?)",
                           df_minute.index[0], inst, d['open'], d['high'], d['low'], d['close'])
            
            if timeframe == "3-Min" and inst == "NIFTY_SPOT":
                process_signals(d['close'])
    except Exception:
        pass 

def process_signals(current_spot):
    global prev_nifty_close
    now_dt = datetime.now()
    now_time = now_dt.time()
    
    # 1. Start Time Filter
    if now_time < TRADE_START_TIME:
        prev_nifty_close = current_spot
        return
        
    # 🔥 2. The New "Late Day" Cutoff Filter
    cutoff_time = TRADE_STOP_EXPIRY if now_dt.weekday() == NIFTY_EXPIRY_DAY else TRADE_STOP_NORMAL
    if now_time >= cutoff_time:
        prev_nifty_close = current_spot
        return # Skip finding new trades, but active trades remain open until 3:30 PM
        
    if prev_nifty_close == 0:
        prev_nifty_close = current_spot
        return
        
    pcr = oi_data["PE"] / oi_data["CE"] if oi_data["CE"] > 0 else 0
    price_move = current_spot - prev_nifty_close
    
    ce_name = instrument_map.get(ce_key_global, "")
    pe_name = instrument_map.get(pe_key_global, "")
    
    if price_move >= TREND_THRESHOLD and pcr >= PCR_BULLISH:
        opt_price = live_prices.get(ce_name, 0)
        if opt_price > 0: execute_mock_trade(ce_name, opt_price, "BUY")
            
    elif price_move <= -TREND_THRESHOLD and pcr <= PCR_BEARISH:
        opt_price = live_prices.get(pe_name, 0)
        if opt_price > 0: execute_mock_trade(pe_name, opt_price, "BUY")
            
    prev_nifty_close = current_spot

def on_message(message):
    global last_processed_minute, tick_buffer
    try:
        feeds = message.get("feeds", {})
        now = datetime.now()
        
        if now.minute != last_processed_minute:
            current_buffer = tick_buffer.copy()
            tick_buffer = []
            last_processed_minute = now.minute
            
            if current_buffer:
                df = pd.DataFrame(current_buffer, columns=['ts', 'instrument', 'ltp'])
                df['ts'] = pd.to_datetime(df['ts']); df.set_index('ts', inplace=True)
                save_candles(df, "1-Min", "Nifty_Candles_1Min")
                if now.minute % 3 == 0: save_candles(df, "3-Min", "Nifty_Candles_3Min")
                if now.minute % 5 == 0: save_candles(df, "5-Min", "Nifty_Candles_5Min")

        for key, data in feeds.items():
            ff = data.get("fullFeed", {})
            if "marketFF" in ff:
                m = ff["marketFF"]
                ltp = m.get("ltpc", {}).get("ltp", 0); vol = m.get("vtt", 0); oi = m.get("oi", 0)
                g = m.get("optionGreeks", {}); name = instrument_map.get(key, key)
                
                live_prices[name] = ltp
                
                if "CE" in name: oi_data["CE"] = oi
                elif "PE" in name: oi_data["PE"] = oi
                pcr = oi_data["PE"] / oi_data["CE"] if oi_data["CE"] > 0 else 0
                
                cursor.execute("INSERT INTO Nifty_Options_Data (instrument, ltp, volume, open_interest, v_wap, iv, delta, theta, gamma, vega, pcr) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               (name, ltp, vol, oi, m.get("atp",0), g.get("iv",0), g.get("delta",0), g.get("theta",0), g.get("gamma",0), g.get("vega",0), pcr))
                tick_buffer.append([now, name, ltp])
                
                if active_trade and active_trade['instrument'] == name:
                    monitor_trade(ltp)
                
            elif "indexFF" in ff:
                ltp = ff["indexFF"]["ltpc"]["ltp"]
                cursor.execute("INSERT INTO Nifty_Tick_Data (instrument, ltp) VALUES (?, ?)", "NIFTY_SPOT", ltp)
                tick_buffer.append([now, "NIFTY_SPOT", ltp])
                
    except Exception:
        pass 

# ==============================
# 6. BOOT SYSTEM
# ==============================
if __name__ == "__main__":
    get_live_keys(token)
    conf = upstox_client.Configuration(); conf.access_token = token
    streamer = upstox_client.MarketDataStreamerV3(upstox_client.ApiClient(conf), ["NSE_INDEX|Nifty 50", ce_key_global, pe_key_global], "full")
    streamer.on("open", lambda: print("🔥 V2.3 QUANT ENGINE ONLINE | Time-Filters & Trailing Stops Active"))
    streamer.on("message", on_message)
    streamer.connect()

    try:
        while True:
            t = datetime.now()
            
            # 🔥 3:30 PM: Auto Square-Off & Shutdown
            if t.hour == 15 and t.minute >= 30:
                print("\n🏁 Market Closed. Initiating EOD Shutdown Sequence...")
                
                if active_trade:
                    current_price = live_prices.get(active_trade['instrument'], active_trade['entry_price'])
                    rupee_pnl = (current_price - active_trade['entry_price']) * active_trade['qty'] if active_trade['side'] == 'BUY' else (active_trade['entry_price'] - current_price) * active_trade['qty']
                    
                    try:
                        cursor.execute("""
                            UPDATE Mock_Trades 
                            SET exit_time = GETDATE(), exit_price = ?, pnl = ?, status = 'CLOSED_EOD' 
                            WHERE status = 'OPEN'
                        """, (current_price, rupee_pnl))
                        print(f"⚠️ EOD SQUARE-OFF: Closed {active_trade['instrument']} @ ₹{current_price} | P&L: ₹{round(rupee_pnl, 2)}")
                    except Exception as e: pass

                try: streamer.disconnect()
                except: pass
                os._exit(0) 
                
            time.sleep(1)
            
    except KeyboardInterrupt: 
        print("\n🛑 Force Killing Quant Engine...")
        os._exit(0)