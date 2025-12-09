#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

//This namespace holds Strategies in this folder and is required. Do not change it. 
namespace NinjaTrader.NinjaScript.Strategies
{
	public class NQMomentumScalper : Strategy
	{
		private ATR atrIndicator;
		private SMA volIndicator;
		
		private double currentDailyPnL = 0;
		private double highestHigh = 0;
		private double lowestLow = 0;
		private bool tradingHalted = false;
		private DateTime currentDate = DateTime.MinValue;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description									= @"NQ Opening Momentum Strategy with SAR logic.";
				Name										= "NQMomentumScalper";
				Calculate									= Calculate.OnBarClose;
				EntriesPerDirection							= 1;
				EntryHandling								= EntryHandling.AllEntries;
				IsExitOnSessionCloseStrategy				= true;
				ExitOnSessionCloseSeconds					= 30;
				IsFillLimitOnTouch							= false;
				MaximumBarsLookBack							= MaximumBarsLookBack.TwoHundredFiftySix;
				OrderFillResolution							= OrderFillResolution.Standard;
				Slippage									= 0;
				StartBehavior								= StartBehavior.WaitUntilFlat;
				TimeInForce									= TimeInForce.Gtc;
				TraceOrders									= false;
				RealtimeErrorHandling						= RealtimeErrorHandling.StopCancelClose;
				StopTargetHandling							= StopTargetHandling.PerEntryExecution;
				BarsRequiredToTrade							= 20;
				// Disable this setting for performance optimization in Strategy Analyzer.
				// IsInstantiatedOnEachOptimizationIteration	= true;
				
				// DEFAULT PARAMETERS
				DailyLossLimit = 100; // $100 Limit for $1000 account (10%)
				ContractSize = 2;     // RECOMMENDED: 2 Micro Contracts max for $1000. 10 is dangerous.
				TrailATR = 3.0;
				VolLength = 20;
				VolMult = 3.0;
				ATRLength = 14;
			}
			else if (State == State.Configure)
			{
				atrIndicator = ATR(ATRLength);
				volIndicator = SMA(Volume, VolLength);
				
				AddPlot(atrIndicator); 
			}
		}

		protected override void OnBarUpdate()
		{
			if (BarsInProgress != 0 || CurrentBar < 20) 
				return;

			// 0. RESET LOGIC FOR NEW DAY
			if (Time[0].Date != currentDate)
			{
				currentDate = Time[0].Date;
				currentDailyPnL = 0;
				tradingHalted = false;
			}
			
			if (tradingHalted) return;

			// 1. UPDATE DAILY PNL (Realized)
			// NinjaTrader makes checking Realtime Daily PnL slightly complex.
			// We check SystemPerformance for the day.
			if (SystemPerformance.AllTrades.Count > 0)
			{
				double dailyRealized = SystemPerformance.AllTrades
					.Where(t => t.ExitTime.Date == currentDate)
					.Sum(t => t.ProfitCurrency);
				
				// Add floating PnL if any
				double floating = Position.GetUnrealizedProfitLoss(PerformanceUnit.Currency, Close[0]);
				
				if ((dailyRealized + floating) <= -DailyLossLimit)
				{
					if (Position.MarketPosition != MarketPosition.Flat)
						ExitLong("DailyStop");
						ExitShort("DailyStop");
					
					tradingHalted = true;
					Print("Daily Loss Limit Hit: " + (dailyRealized + floating));
					return;
				}
			}

			// 2. TIME LOGIC (Exchange Time - typically Central Time for CME in NinjaTrader)
			// Strategy designed for 09:30 - 15:45 ET.
			// 09:30 ET = 08:30 CT.
			// We wait for first bar to close. If 5m bar, closing time 08:35 CT.
			int timeNow = ToTime(Time[0]);
			
			// Adjust these if your data is not in Central Time
			int startTime = 83500; // 08:35:00 AM CT
			int endTime = 144500;  // 02:45:00 PM CT

			// MARKET CLOSE
			if (timeNow >= endTime)
			{
				if (Position.MarketPosition != MarketPosition.Flat)
				{
					ExitLong();
					ExitShort();
				}
				return;
			}

			// 3. INITIAL ENTRY (First Bar)
			if (timeNow == startTime && Position.MarketPosition == MarketPosition.Flat)
			{
				if (Close[0] > Open[0])
				{
					EnterLong(ContractSize, "LongOpen");
					highestHigh = High[0];
				}
				else
				{
					EnterShort(ContractSize, "ShortOpen");
					lowestLow = Low[0];
				}
				return;
			}

			// 4. SAR LOGIC
			if (Position.MarketPosition != MarketPosition.Flat)
			{
				// Update Extremes
				if (Position.MarketPosition == MarketPosition.Long)
					highestHigh = Math.Max(highestHigh, High[0]);
				else if (Position.MarketPosition == MarketPosition.Short)
					lowestLow = Math.Min(lowestLow, Low[0]);

				bool reversalTriggered = false;

				// A. TRAIL REVERSAL
				double revDist = atrIndicator[0] * TrailATR;

				if (Position.MarketPosition == MarketPosition.Long)
				{
					if (Close[0] < (highestHigh - revDist))
					{
						EnterShort(ContractSize, "TrailRevShort"); // Reverse
						lowestLow = Low[0];
						reversalTriggered = true;
					}
				}
				else if (Position.MarketPosition == MarketPosition.Short)
				{
					if (Close[0] > (lowestLow + revDist))
					{
						EnterLong(ContractSize, "TrailRevLong"); // Reverse
						highestHigh = High[0];
						reversalTriggered = true;
					}
				}

				// B. VOLUME SPIKE REVERSAL
				if (!reversalTriggered)
				{
					bool isVolSpike = Volume[0] > (volIndicator[0] * VolMult);

					if (Position.MarketPosition == MarketPosition.Long)
					{
						// Spike + Bearish Candle
						if (isVolSpike && Close[0] < Close[1])
						{
							EnterShort(ContractSize, "VolRevShort");
							lowestLow = Low[0];
						}
					}
					else if (Position.MarketPosition == MarketPosition.Short)
					{
						// Spike + Bullish Candle
						if (isVolSpike && Close[0] > Close[1])
						{
							EnterLong(ContractSize, "VolRevLong");
							highestHigh = High[0];
						}
					}
				}
			}
		}

		#region Properties
		[NinjaScriptProperty]
		[Range(1, int.MaxValue)]
		[Display(Name="ContractSize", Description="Contracts to trade", Order=1, GroupName="Parameters")]
		public int ContractSize
		{ get; set; }

		[NinjaScriptProperty]
		[Range(1, double.MaxValue)]
		[Display(Name="DailyLossLimit", Description="Max Loss in $", Order=2, GroupName="Parameters")]
		public double DailyLossLimit
		{ get; set; }

		[NinjaScriptProperty]
		[Range(0.1, double.MaxValue)]
		[Display(Name="TrailATR", Description="ATR Multiplier for Trail", Order=3, GroupName="Parameters")]
		public double TrailATR
		{ get; set; }
		
		[NinjaScriptProperty]
		[Range(0.1, double.MaxValue)]
		[Display(Name="VolMult", Description="Volume Multiplier", Order=4, GroupName="Parameters")]
		public double VolMult
		{ get; set; }
		
		[NinjaScriptProperty]
		[Range(1, int.MaxValue)]
		[Display(Name="VolLength", Description="Volume MA Length", Order=5, GroupName="Parameters")]
		public int VolLength
		{ get; set; }
		
		[NinjaScriptProperty]
		[Range(1, int.MaxValue)]
		[Display(Name="ATRLength", Description="ATR Length", Order=6, GroupName="Parameters")]
		public int ATRLength
		{ get; set; }
		#endregion
	}
}
