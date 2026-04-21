# 📈 Distributed Quantitative Trading Desk

A multi-node, autonomous algorithmic trading system built in Python. This project interfaces with the Upstox API to process live WebSocket market data, calculate options greeks/PCR, and execute mock trades with institutional-grade risk management.

## 🏗️ System Architecture

This system is designed as a distributed architecture, running across three separate terminals to avoid API bottlenecking and ensure maximum thread stability.

### 1. The Execution Engine (`main.py`)
The core trading algorithm focused on the Nifty 50 Index.
* **Dynamic Options Routing:** Automatically fetches the live ATM Call and Put instrument keys.
* **Confluence Logic:** Executes trades based on a combination of 3-minute Spot momentum and live Put-Call Ratio (PCR) thresholds.
* **Risk Management:** * Auto-calculated position sizing based on live NSE lot sizes.
  * Trailing Stop Loss (TSL) memory protocol to lock in breakeven on winning trades.
  * Expiry-Day Time Locks (halts trading at 2:45 PM on Tuesdays to avoid gamma decay traps).
  * 3:30 PM End-of-Day automatic square-off sequence.

### 2. The Live F&O Scanner (`live_scanner.py`)
A background intelligence gatherer tracking the broader equity market.
* **WebSocket Management:** Subscribes to 180+ premium F&O stocks simultaneously.
* **Dual-Layer Filtering:** Automatically purges stocks below ₹200 to protect API rate limits and avoid illiquid/high-lot-size traps.
* **Telegram Integration:** Pushes real-time alerts to a mobile device when strict volume and RSI confluence metrics are met on the 5-minute timeframe.

### 3. The Market Internals Dashboard (`heavyweight_radar.py`)
A live terminal UI designed to filter out index fake-outs.
* Calculates a live "Internal Strength Score" by tracking the exact index weightings of the top 7 Nifty heavyweights (HDFC Bank, Reliance, ICICI, etc.).
* Prevents the execution engine from taking index trades that contradict the movement of the heavyweights.

### 4. Data Pipeline & Analytics
* **SQL Server Integration:** Uses `pyodbc` to log every tick, dynamically built OHLC candles, options greeks, and trade P&L into a local Microsoft SQL Server. Includes auto-repair functions for missing tables.
* **End of Day Analyzer:** A standalone script that pulls the day's SQL logs into a multi-tab Pandas Excel report for deep quantitative strategy review.

## 🚀 Technologies Used
* **Language:** Python 3.x
* **Data Handling:** Pandas, NumPy
* **Database:** Microsoft SQL Server (SSMS), `pyodbc`
* **Broker API:** Upstox API V3, WebSockets
* **Alerting:** Telegram Bot API

## ⚠️ Disclaimer
This repository is for educational and portfolio purposes only. The strategies coded within are currently configured for a Mock Database ledger. Do not use these scripts with real capital without implementing server-side (Bracket/Cover) hard stops and hosting on a stable VPS infrastructure.
