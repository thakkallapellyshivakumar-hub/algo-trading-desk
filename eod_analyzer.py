import pyodbc
import pandas as pd
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("📊 Generating Full End-of-Day Quant Report...")

# 1. Connect to your local SQL Server
conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=localhost\SQLEXPRESS;"  
    "DATABASE=master;"               
    "Trusted_Connection=yes;"
)

try:
    conn = pyodbc.connect(conn_str)
    
    # 2. Extract ALL Data
    print("📥 Pulling Trades...")
    df_trades = pd.read_sql("SELECT * FROM Mock_Trades ORDER BY entry_time DESC", conn)
    
    print("📥 Pulling Options Data & PCR...")
    df_options = pd.read_sql("SELECT * FROM Nifty_Options_Data ORDER BY timestamp DESC", conn)
    
    print("📥 Pulling 1-Minute Candles...")
    df_candles_1m = pd.read_sql("SELECT * FROM Nifty_Candles_1Min ORDER BY candle_time DESC", conn)

    print("📥 Pulling 3-Minute Candles...")
    df_candles_3m = pd.read_sql("SELECT * FROM Nifty_Candles_3Min ORDER BY candle_time DESC", conn)

    print("📥 Pulling 5-Minute Candles...")
    df_candles_5m = pd.read_sql("SELECT * FROM Nifty_Candles_5Min ORDER BY candle_time DESC", conn)

    print("📥 Pulling Nifty Spot Tick Data...")
    df_ticks = pd.read_sql("SELECT * FROM Nifty_Tick_Data ORDER BY timestamp DESC", conn)
    
    conn.close()

    # 3. Create a Multi-Tab Excel File
    filename = f"Full_Quant_Report_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    print(f"📝 Writing data to Excel (This might take a moment due to tick data)...")
    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        df_trades.to_excel(writer, sheet_name='Trade_Journal', index=False)
        df_options.to_excel(writer, sheet_name='Options_Greeks_PCR', index=False)
        df_candles_1m.to_excel(writer, sheet_name='1Min_Candles', index=False)
        df_candles_3m.to_excel(writer, sheet_name='3Min_Candles', index=False)
        df_candles_5m.to_excel(writer, sheet_name='5Min_Candles', index=False)
        df_ticks.to_excel(writer, sheet_name='Nifty_Ticks', index=False)
        
    print(f"\n✅ SUCCESS! All data saved to: {filename}")
    
    # 4. Print a quick summary to your terminal
    if not df_trades.empty:
        total_pnl = df_trades['pnl'].sum()
        wins = len(df_trades[df_trades['pnl'] > 0])
        total_trades = len(df_trades)
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        
        print("\n📈 SYSTEM PERFORMANCE SUMMARY:")
        print(f"Total Trades Taken: {total_trades}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Total Net P&L: ₹{total_pnl:.2f}")

except Exception as e:
    print(f"❌ Error connecting to database: {e}")