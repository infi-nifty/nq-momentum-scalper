import backtrader as bt
import datetime
import yfinance as yf
import pandas as pd

class OpeningMomentumStrategy(bt.Strategy):
    params = (
        ('daily_loss_limit', 200.0),  # Max daily loss ($200 = 4% of 5000)
        ('fixed_size', 1),            # 1 MNQ Contract
        ('trail_atr', 3.0),           # Reversal distance in ATR multiples
        ('vol_multiplier', 3.0),      # Volume spike threshold
        ('multiplier', 2.0),          # MNQ Futures Multiplier ($2/point)
        ('debug', True)
    )

    def log(self, txt, dt=None):
        if self.params.debug:
            dt = dt or self.datas[0].datetime.datetime(0)
            print(f'{dt.isoformat()} {txt}')

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low
        self.volume = self.datas[0].volume
        
        # Indicators
        self.atr = bt.indicators.ATR(self.datas[0], period=14)
        self.vol_ma = bt.indicators.SMA(self.volume, period=20)

        # State tracking
        self.current_day = None
        self.start_day_value = None
        self.highest_high = None
        self.lowest_low = None
        self.trading_halted = False
        
        # We need to track realized PnL manually for the daily limit
        # because broker.getvalue() fluctuates with open positions.
        self.daily_realized_pnl = 0.0

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        
        pnl = trade.pnlcomm
        self.daily_realized_pnl += pnl
        self.log(f'TRADE CLOSED: PnL: ${pnl:.2f} | Daily Realized: ${self.daily_realized_pnl:.2f}')

    def start_of_day_reset(self):
        self.daily_realized_pnl = 0.0
        self.trading_halted = False
        self.start_day_value = self.broker.getvalue()
        self.log(f'--- START OF DAY: {self.current_day} | Equity: ${self.start_day_value:.2f} ---')

    def check_daily_loss_limit(self):
        # Calculate current daily PnL (Realized + Unrealized)
        unrealized_pnl = 0.0
        if self.position:
            # Approximate unrealized PnL
            diff = self.dataclose[0] - self.position.price
            if self.position.size < 0: diff = -diff
            unrealized_pnl = diff * self.params.multiplier * abs(self.position.size)
        
        total_daily_pnl = self.daily_realized_pnl + unrealized_pnl
        
        if total_daily_pnl < -self.params.daily_loss_limit:
            self.log(f'DAILY LOSS LIMIT HIT (${total_daily_pnl:.2f}). CLOSING ALL & HALTING.')
            self.close()
            self.trading_halted = True
            return True
        return False

    def reverse_position(self, signal_type):
        ''' Closes current position and opens opposite '''
        size = self.params.fixed_size
        
        if self.position.size > 0: # Long -> Short
            self.log(f'REVERSAL ({signal_type}): Long -> Short')
            self.close() 
            self.sell(size=size)
            self.lowest_low = self.datalow[0] # Reset extreme
            
        elif self.position.size < 0: # Short -> Long
            self.log(f'REVERSAL ({signal_type}): Short -> Long')
            self.close()
            self.buy(size=size)
            self.highest_high = self.datahigh[0] # Reset extreme
            
        else: # Flat -> Enter (shouldn't happen in purely logic, but just in case)
             pass

    def next(self):
        dt = self.datas[0].datetime.datetime(0)
        current_date = dt.date()
        current_time = dt.time()

        # 0. New Day Logic
        if self.current_day != current_date:
            self.current_day = current_date
            self.start_of_day_reset()

        if self.trading_halted:
            return

        # 1. Check Daily Loss
        if self.check_daily_loss_limit():
            return

        # Define Times
        market_open = datetime.time(9, 30)
        market_close = datetime.time(15, 45) # Force exit
        
        # Calculate when the "First Bar" Logic applies
        # If we use 5m bars: 09:30 bar closes at 09:35. We act then.
        first_bar_close = (datetime.datetime.combine(datetime.date.today(), market_open) + datetime.timedelta(minutes=5)).time()

        # 2. MARKET CLOSE EXIT
        if current_time >= market_close:
            if self.position:
                self.log('Market Close - Flattening')
                self.close()
            return

        # 3. ENTRY: FIRST BAR OF DAY
        # We check strictly at the bar that completes the first 5 minutes
        if current_time == first_bar_close:
            if not self.position:
                if self.dataclose[0] > self.dataopen[0]:
                    self.log('FIRST BAR LONG: Close > Open')
                    self.buy(size=self.params.fixed_size)
                    self.highest_high = self.datahigh[0]
                else: 
                    self.log('FIRST BAR SHORT: Close < Open')
                    self.sell(size=self.params.fixed_size)
                    self.lowest_low = self.datalow[0]
            return

        # 4. TRADE MANAGEMENT (SAR)
        if self.position:
            
            # Update Extremes
            if self.position.size > 0:
                self.highest_high = max(self.highest_high, self.datahigh[0])
            elif self.position.size < 0:
                self.lowest_low = min(self.lowest_low, self.datalow[0])

            # --- REVERSAL LOGIC ---
            reversal_triggered = False
            
            # A. TRAILING REVERSAL (Price moves against trend by X ATR)
            reversal_dist = self.atr[0] * self.params.trail_atr
            
            if self.position.size > 0: # We are Long
                if self.dataclose[0] < (self.highest_high - reversal_dist):
                    self.reverse_position("Trailing Stop")
                    reversal_triggered = True
            
            elif self.position.size < 0: # We are Short
                if self.dataclose[0] > (self.lowest_low + reversal_dist):
                    self.reverse_position("Trailing Stop")
                    reversal_triggered = True

            # B. VOLUME REVERSAL (Spike + Counter-Trend Candle)
            # Only check if Trail didn't already trigger
            if not reversal_triggered:
                is_vol_spike = self.volume[0] > (self.vol_ma[0] * self.params.vol_multiplier)
                
                if is_vol_spike:
                    if self.position.size > 0: # Long
                        # If huge volume and we close LOWER than prev close (Bearish shift)
                        if self.dataclose[0] < self.dataclose[-1]:
                            self.reverse_position("Volume Spike Bearish")
                    
                    elif self.position.size < 0: # Short
                        # If huge volume and we close HIGHER than prev close (Bullish shift)
                        if self.dataclose[0] > self.dataclose[-1]:
                            self.reverse_position("Volume Spike Bullish")

if __name__ == '__main__':
    cerebro = bt.Cerebro()

    # ADD STRATEGY
    cerebro.addstrategy(OpeningMomentumStrategy)

    # DATA
    # Attempting to download NQ=F (E-mini Nasdaq 100)
    # Note: 1m data for futures on yfinance is limited. We might get 5m or 1h depending on availability.
    # For a robust backtest, use "QQQ" as a proxy or import CSV data.
    print("Downloading Data for NQ=F...")
    data_source = yf.download("NQ=F", period="6mo", interval="5m", progress=False)
    
    
    if len(data_source) == 0:
        print("Failed to download NQ=F data. Trying QQQ as proxy.")
        data_source = yf.download("QQQ", period="6mo", interval="5m", progress=False)
        
    
    # FIX: Flatten MultiIndex columns if present (common with newer yfinance)
    if isinstance(data_source.columns, pd.MultiIndex):
        data_source.columns = data_source.columns.get_level_values(0)
    
    # CONVERT TO EASTERN TIME
    if data_source.index.tz is None:
        # Assume UTC if naive (or just localize to Eastern if we are sure, but safer to assume UTC then convert)
        data_source.index = data_source.index.tz_localize('UTC').tz_convert('US/Eastern')
        print("Data localized to UTC and converted to US/Eastern")
    else:
        data_source.index = data_source.index.tz_convert('US/Eastern')
        print("Data converted to US/Eastern")

    # Clean up any NaN rows
    data_source.dropna(inplace=True)

    # Create Backtrader Data Feed
    data = bt.feeds.PandasData(dataname=data_source)
    cerebro.adddata(data)

    # BROKER SETTINGS
    cerebro.broker.setcash(5000.0)
    
    # MNQ Futures settings (Micro NQ)
    # Commission: ~$0.60 per side for Micros ($1.20 round turn)
    # Multiplier: $2 per point
    # Margin: NinjaTrader intraday margin for Micros is ~$50-$100
    cerebro.broker.setcommission(commission=0.6, margin=50.0, mult=2.0) 
    
    # To simulate slippage more accurately for market orders
    cerebro.broker.set_slippage_perc(0.0001) # 0.01% slippage 

    # ADD ANALYZERS
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())

    results = cerebro.run()
    strat = results[0]

    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
    
    # PRINT ANALYZER RESULTS
    trade_analysis = strat.analyzers.trades.get_analysis()
    drawdown_analysis = strat.analyzers.drawdown.get_analysis()

    print("\n========== BACKTEST RESULTS ==========")
    
    if trade_analysis.get('total', {}).get('total', 0) > 0:
        total_trades = trade_analysis.total.total
        won_trades = trade_analysis.won.total
        lost_trades = trade_analysis.lost.total
        win_rate = (won_trades / total_trades) * 100
        
        # PnL
        pnl_net = trade_analysis.pnl.net.total
        
        # Drawdown
        max_drawdown = drawdown_analysis.max.drawdown
        max_drawdown_len = drawdown_analysis.max.len
        
        print(f"Total Trades: {total_trades}")
        print(f"Win Rate: {win_rate:.2f}% ({won_trades} Won / {lost_trades} Lost)")
        print(f"Net PnL: ${pnl_net:.2f}")
        print(f"Max Drawdown: {max_drawdown:.2f}%")
        print(f"Max Drawdown Length: {max_drawdown_len} bars")
    else:
        print("No trades were closed during this period.")
    
    print("======================================")
