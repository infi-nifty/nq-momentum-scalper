import backtrader as bt
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import random
from strategy import OpeningMomentumStrategy
import sys
import os

# Suppress console output during backtest (Commented out to debug)
# sys.stdout = open(os.devnull, 'w')

def run_backtest():
    cerebro = bt.Cerebro()
    
    # Add Strategy with correct parameters
    cerebro.addstrategy(OpeningMomentumStrategy, 
                        daily_loss_limit=200.0,
                        fixed_size=1,
                        trail_atr=3.0,
                        vol_multiplier=3.0,
                        multiplier=2.0)

    # Data Loading (Same as strategy.py)
    try:
        data_source = yf.download("NQ=F", period="59d", interval="5m", progress=False)
        if len(data_source) == 0:
             data_source = yf.download("QQQ", period="59d", interval="5m", progress=False)
    except Exception:
        data_source = yf.download("QQQ", period="59d", interval="5m", progress=False)

    if isinstance(data_source.columns, pd.MultiIndex):
        data_source.columns = data_source.columns.get_level_values(0)

    if data_source.index.tz is None:
        data_source.index = data_source.index.tz_localize('UTC').tz_convert('US/Eastern')
    else:
        data_source.index = data_source.index.tz_convert('US/Eastern')
    
    data_source.dropna(inplace=True)
    
    data = bt.feeds.PandasData(dataname=data_source)
    cerebro.adddata(data)

    # Broker Settings ($5000, 1 MNQ)
    cerebro.broker.setcash(5000.0)
    cerebro.broker.setcommission(commission=0.6, margin=50.0, mult=2.0)
    cerebro.broker.set_slippage_perc(0.0001)

    # Analyzers
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # Run
    results = cerebro.run()
    return results[0]

# --- MAIN ANALYSIS ---
# sys.stdout = sys.__stdout__ # Restore print
print("Running base backtest for simulation...")
strat = run_backtest()

# Extract Trades
daily_pnls = {}

# Access strategy internal trade list
trade_list = strat._trades[strat.datas[0]][0] # Closed trade list

print(f"Total Closed Trades extracted: {len(trade_list)}")

for trade in trade_list:
    # Get date of trade CLOSE
    # Use dtclose (float) and convert to date
    date = trade.dtclose
    date_key = bt.num2date(date).date()
    
    pnl = trade.pnlcomm
    
    if date_key not in daily_pnls:
        daily_pnls[date_key] = 0.0
    daily_pnls[date_key] += pnl

pnl_sequence = list(daily_pnls.values())
days = len(pnl_sequence)

print(f"Total Trading Days: {days}")
print(f"Average Daily PnL: ${np.mean(pnl_sequence):.2f}")

# --- MONTE CARLO SIMULATION ---
SIMULATIONS = 1000
STARTING_EQUITY = 5000.0

final_equities = []
max_drawdowns = []
all_curves = []

print(f"Running {SIMULATIONS} Monte Carlo Simulations (Shuffling Days)...")

for i in range(SIMULATIONS):
    # Bootstrapping (Resample with Replacement)
    # This varies the Final Equity and tests "What if we had more/less luck with good days?"
    daily_seq = random.choices(pnl_sequence, k=days)
    
    # Calculate Curve
    equity = [STARTING_EQUITY]
    peak = STARTING_EQUITY
    drawdown = 0.0
    
    for pnl in daily_seq:
        new_val = equity[-1] + pnl
        equity.append(new_val)
        
        # DD Calc
        if new_val > peak:
            peak = new_val
        dd = (peak - new_val) / peak
        if dd > drawdown:
            drawdown = dd
            
    final_equities.append(equity[-1])
    max_drawdowns.append(drawdown * 100) # Percentage
    all_curves.append(equity)

# --- PLOTTING ---
plt.figure(figsize=(12, 8))

# 1. Equity Curves
plt.subplot(2, 2, 1)
plt.title(f"Monte Carlo: 1000 Equity Curves (Shuffle)")
plt.ylabel("Account Equity ($)")
plt.xlabel("Trading Days")
for curve in all_curves[:100]: # Plot 100 random ones
    plt.plot(curve, color='gray', alpha=0.1)
# Plot Average
avg_curve = np.mean(all_curves, axis=0)
plt.plot(avg_curve, color='blue', linewidth=2, label='Average')
plt.axhline(y=STARTING_EQUITY, color='r', linestyle='--')
plt.legend()

# 2. Final Equity Distribution
plt.subplot(2, 2, 2)
plt.title("Distribution of Final Equity")
plt.hist(final_equities, bins=10, color='green', alpha=0.7)
plt.axvline(x=STARTING_EQUITY, color='red', linestyle='--', label='Start')
plt.xlabel("Final Equity ($)")
plt.legend()

# 3. Max Drawdown Distribution
plt.subplot(2, 2, 3)
plt.title("Distribution of Max Drawdown")
plt.hist(max_drawdowns, bins=10, color='red', alpha=0.7)
plt.xlabel("Max Drawdown (%)")

# 4. Metrics Text
plt.subplot(2, 2, 4)
plt.axis('off')
roi_avg = np.mean(final_equities) - STARTING_EQUITY
risk_of_ruin = sum(1 for x in final_equities if x < 2500) / SIMULATIONS * 100 # <50% equity left
dd_95 = np.percentile(max_drawdowns, 95)

text_str = (
    f"Simulation Metrics (Based on Reverted Strategy):\n\n"
    f"Mean Final Equity: ${np.mean(final_equities):.2f}\n"
    f"Mean Net Profit: ${roi_avg:.2f}\n"
    f"Best Case: ${np.max(final_equities):.2f}\n"
    f"Worst Case: ${np.min(final_equities):.2f}\n\n"
    f"95% Confidence Drawdown: < {dd_95:.2f}%\n"
    f"Risk of Ruin (<50%): {risk_of_ruin:.1f}%"
)
plt.text(0.1, 0.5, text_str, fontsize=12)

plt.tight_layout()
plt.savefig('monte_carlo_results.png')
print("Simulation complete. Saved to monte_carlo_results.png")
