# NQ Opening Momentum Scalper

A futures trading strategy designed for the Nasdaq-100 (NQ), focusing on catching the opening momentum and scalping subsequent trend changes using a Stop-and-Reverse (SAR) logic.

## Strategy Logic

1.  **Opening Entry (09:30 ET)**:
    *   Waits for the first 5-minute bar of the NYSE session to close (09:35 ET).
    *   **Long** if Close > Open.
    *   **Short** if Close < Open.

2.  **Trade Management (Always In)**:
    *   The strategy stays in the market until the session close (15:45 ET) or the Daily Loss Limit is hit.
    *   It flips direction (Reverse) based on two conditions:
        *   **Trailing Stop**: If price moves against the extreme of the current trade by **3.0 ATR**, reverse position.
        *   **Volume Spike**: If volume is **3.0x** the usage average AND the candle is counter-trend, reverse position immediately.

3.  **Risk Management**:
    *   **Daily Loss Limit**: Hard stop at **$2,000** loss per day. If hit, all positions are closed and trading halts until the next day.
    *   **Position Size**: Fixed at 1 MNQ Contract (Micro).

## Performance (Backtest Benchmark)
*   **Period**: Last 60 Days (Oct - Dec 2025)
*   **Net Profit**: +$1,945.17 (On $5,000 Starting Equity)
*   **Win Rate**: ~35% (Trend following profile)
*   **Drawdown**: ~33%
*   *Note: Tested on MNQ (Micro NQ) settings.*

## How to Run

1.  **Install Requirements**:
    ```bash
    ./venv/bin/pip install -r requirements.txt
    ```

2.  **Run Strategy**:
    ```bash
    ./venv/bin/python strategy.py
    ```

## Configuration
Edit `strategy.py` to change parameters:
```python
params = (
    ('daily_loss_limit', 2000.0), # Max daily loss
    ('trail_atr', 3.0),           # Sensitivity of reversal (Lower = More Trades)
    ('vol_multiplier', 3.0),      # Sensitivity of volume spikes
    ...
)
```
