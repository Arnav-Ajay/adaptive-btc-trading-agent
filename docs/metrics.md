# Trading Metrics

This document describes the market metrics currently used by the project.

It reflects the code that is active today, not the long-term target design.

## Last Price

- Definition: the close of the most recent candle in the trading lookback window.
- Code: [app/features/indicators.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/indicators.py)
- Financial meaning: the latest market price the trading loop sees.
- High or low: this has no standalone "good" or "bad" interpretation. It matters relative to prior buys, moving averages, and thresholds.
- Project perspective: used as the strategy reference price, the paper broker mark price, and the execution reference price.

Example:
- If the last price is `70,284.96` and the last DCA buy was `70,210.01`, then BTC is slightly above your latest buy, so the DCA drop trigger is unlikely to fire.

## ATR

- Full name: Average True Range.
- Code: [app/features/atr.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/atr.py)
- Calculation:
  - For each candle after the first, compute the true range as the maximum of:
    - `high - low`
    - `abs(high - previous_close)`
    - `abs(low - previous_close)`
  - Average the last `14` true ranges.
- Financial meaning: recent volatility, measured in price units.
- High ATR:
  - BTC has been moving more per candle.
  - Markets are more volatile.
  - Stops based on ATR should usually be wider.
- Low ATR:
  - BTC has been relatively stable.
  - Markets are quieter.
  - Stops based on ATR can be tighter.
- Project perspective:
  - Currently used by the swing strategy to size a candidate stop loss.
  - Not yet used in a full active-trade stop-loss lifecycle.

Example:
- ATR `54.74` on BTC around `70k` means average recent one-minute movement is about `$55`, which is fairly calm.

## RSI

- Full name: Relative Strength Index.
- Code: [app/features/rsi.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/rsi.py)
- Calculation:
  - Compute close-to-close deltas.
  - Separate them into gains and losses.
  - Average the last `14` gains and the last `14` losses.
  - Compute `RS = avg_gain / avg_loss`.
  - Compute `RSI = 100 - 100 / (1 + RS)`.
- Financial meaning: recent directional momentum on a `0` to `100` scale.
- High RSI:
  - Recent upside has dominated.
  - Can indicate strong bullish momentum.
  - Very high values can also suggest an overextended market.
- Low RSI:
  - Recent downside has dominated.
  - Can indicate bearish momentum.
  - Very low values can also suggest oversold conditions.
- Project perspective:
  - Used in regime detection.
  - Used in swing entry filtering.

Examples:
- RSI `68.40`: bullish momentum, but current swing logic treats it as too high for a fresh swing entry because it requires `rsi < 65`.
- RSI `17.93`: very weak recent momentum, strongly supportive of a bearish classification.

## EMA Fast and EMA Slow

- Full name: Exponential Moving Average.
- Code: [app/features/macd.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/macd.py)
- Calculation:
  - EMA applies more weight to recent prices than older prices.
  - The project currently uses:
    - fast EMA period `12`
    - slow EMA period `26`
- Financial meaning:
  - Fast EMA reacts quickly.
  - Slow EMA reacts more smoothly.
  - Their relative position is a basic trend signal.
- If fast EMA is above slow EMA:
  - short-term trend is stronger than medium-term trend
  - bullish trend bias
- If fast EMA is below slow EMA:
  - short-term trend is weaker than medium-term trend
  - bearish trend bias
- Project perspective:
  - Used directly in regime detection.
  - Used directly in swing entry filtering.

Examples:
- `ema_fast > ema_slow` with RSI above `55` gives a bullish regime.
- `ema_fast < ema_slow` with RSI below `45` gives a bearish regime.

## MACD

- Full name: Moving Average Convergence Divergence.
- Code: [app/features/macd.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/macd.py)
- Calculation:
  - `MACD = EMA(12) - EMA(26)`
- Financial meaning:
  - Positive MACD means short-term trend is above medium-term trend.
  - Negative MACD means short-term trend is below medium-term trend.
- High positive MACD:
  - strong bullish momentum
- Deep negative MACD:
  - strong bearish momentum
- Project perspective:
  - included in the feature set
  - paired with signal and histogram for swing filtering

Example:
- MACD `-6.50` means the fast EMA is below the slow EMA, which confirms bearish momentum.

## MACD Signal

- Definition: a `9`-period EMA of the MACD series.
- Code: [app/features/macd.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/macd.py)
- Financial meaning:
  - smoother version of MACD
  - helps judge whether momentum is accelerating or decelerating
- Project perspective:
  - used indirectly through the histogram

Example:
- If MACD is below the signal line, momentum is weakening versus its recent trend.

## MACD Histogram

- Definition: `MACD - signal`
- Code: [app/features/macd.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/macd.py)
- Financial meaning:
  - positive histogram means MACD is above its signal line
  - negative histogram means MACD is below its signal line
  - often read as momentum acceleration or deceleration
- Positive histogram:
  - improving bullish momentum
- Negative histogram:
  - weakening momentum or strengthening bearish pressure
- Project perspective:
  - current swing entry requires `macd_histogram > 0`
  - this was recently fixed to use a real MACD series instead of a degenerate one-value signal calculation

Examples:
- Histogram `3.36`: mildly improving bullish momentum
- Histogram `-25.11`: bearish momentum is materially stronger than its recent smoothed trend
