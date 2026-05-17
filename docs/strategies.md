# Strategy Document (Conceptual Layer)

This document defines the **conceptual design space** of the trading system.

It is NOT a reflection of current implementation.
Instead, it captures:

* core strategy primitives
* decision structures
* entry / exit logic types
* risk management approaches
* regime-aware behavior

The goal is to evolve this into a **complete decision engine framework**.

---

## Optional LLM Overlay

The current project also experiments with an optional score-based LLM review layer.

This overlay:

* sits after deterministic signal generation
* can only `allow`, `reduce`, or `block` existing signals
* emits a `decision` object with `confidence` and `score`
* is replayed in the evaluation harness as:
  * `llm_hard`
  * `llm_soft`
  * `llm_weighted`

It does not replace the strategy primitives below.

---

## 1. Strategy Primitives

All strategies in the system reduce to a combination of these primitives:

### 1.1 Mean Reversion

Concept:

* price deviates from average → expected to revert

Examples:

* DCA
* RSI oversold
* Bollinger Band lower touch

Strengths:

* works well in sideways markets

Weaknesses:

* fails in strong downtrends

---

### 1.2 Momentum / Trend Following

Concept:

* price is moving in a direction → continue in same direction

Examples:

* EMA crossover
* MACD positive histogram
* breakout entries

Strengths:

* captures large moves

Weaknesses:

* suffers in choppy markets

---

### 1.3 Volatility-Based Control

Concept:

* position sizing and exits depend on volatility

Examples:

* ATR stop-loss
* volatility-adjusted position sizing

Strengths:

* adapts to market conditions

Weaknesses:

* does not generate edge alone

---

### 1.4 Timing / Entry Refinement

Concept:

* improve entry quality within another strategy

Examples:

* pullback entry in uptrend
* RSI reclaim after oversold
* candle confirmation

Strengths:

* reduces poor entries

Weaknesses:

* can reduce trade frequency too much

---

## 2. Entry Types

### 2.1 Blind Accumulation

* fixed rule-based buying
* no timing or filtering

Example:

* basic DCA

---

### 2.2 Dip-Based Entry (Mean Reversion)

* buy after price drops a threshold

Example:

* DCA with drop %

---

### 2.3 Momentum Entry

* buy when trend conditions are strong

Example:

* EMA + MACD confirmation

---

### 2.4 Pullback in Trend

* buy dips within an uptrend

Example:

* trend filter + retracement

---

### 2.5 Breakout Entry (Future)

* buy when price breaks resistance

---

## 3. Exit Types

### 3.1 Stop Loss

* exit when loss threshold is hit

Types:

* fixed %
* ATR-based

---

### 3.2 Take Profit

* exit at predefined gain

---

### 3.3 Signal-Based Exit

* exit when indicators reverse

Example:

* MACD flips
* EMA crossover reversal

---

### 3.4 No Follow-Through Exit

* exit if trade does not move favorably within time window

---

### 3.5 Time-Based Exit (Future)

* exit after fixed time duration

---

### 3.6 Trailing Stop (Future)

* dynamic stop that moves with price

---

## 4. Risk Management

### 4.1 Position Sizing

* fixed size
* % of portfolio

---

### 4.2 Volatility-Based Sizing (Future)

* smaller size in high volatility
* larger size in low volatility

---

### 4.3 Portfolio Guard

* halt trading after drawdown threshold

---

### 4.4 Capital Allocation

* prevent overuse of capital

---

## 5. Regime Detection

### 5.1 Current Approach

* EMA + RSI based classification

States:

* Bullish
* Bearish
* Sideways

---

### 5.2 Conceptual Limitation

* simplistic
* no volume or macro signals

---

## 6. Regime → Strategy Mapping

This is the most critical system-level behavior.

### 6.1 Desired Mapping

Bullish:

* Momentum
* Pullback entries

Sideways:

* Mean reversion

Bearish:

* Defensive behavior
* reduced or no buying

---

### 6.2 Current Gap

* swing permissions now have a basic regime gate, but not yet a richer regime-specific policy
* broader portfolio intent is still incomplete beyond DCA-specific controls

---

## 7. Strategy Structures

### 7.1 Single Strategy

* only one logic active

---

### 7.2 Hybrid Strategy

* multiple strategies active together

Example:

* DCA + Momentum

---

### 7.3 Conditional Strategy (Desired)

* strategies activated only under conditions

Example:

* if bullish → enable momentum
* if sideways → enable DCA
* if bearish → disable buying

---

## 8. Portfolio Intent (Missing Layer)

The system currently lacks explicit intent.

## 8.1 Possible Modes

* Accumulation
* Trading
* Capital Preservation

---

## 9. Known System Gaps

### 9.1 No strict regime enforcement

* strategies run even in unfavorable conditions

### 9.2 DCA has no exit philosophy

* purely accumulation

## 9.3 No volatility-aware sizing

* position size not adjusted dynamically

## 9.4 No portfolio-level decision layer

* system reacts per signal, not per objective

---

## 10. Core System Equation

Every strategy can be expressed as:

Strategy = Entry + Exit + Risk + Market Condition

---

## 11. Guiding Principle

There are not many unique strategies.

Most systems are combinations of:

* mean reversion
* momentum
* volatility control
* timing refinement

The edge comes from:

* when to apply them
* how to combine them
* how to control risk

---

## 12. Additional Concepts from Research

### 12.1 Breakout-Based Trading

Concept:

* price breaks structure → continuation move

Key ideas:

* breakout works better in direction of trend fileciteturn18file1turn18file2
* often follows consolidation

Enhancements:

* combine with RSI / trend filters
* avoid false breakouts in sideways markets

### 12.2 Structured Risk-Reward Execution

Concept:

* predefined SL and multiple TP levels

New additions:

* multiple take profits (TP1, TP2, TP3) fileciteturn18file1
* ATR-based stop loss
* visual risk/reward zones

Insight:

* execution structure is as important as entry

### 12.3 Statistical Mean Reversion

Concept:

* price deviations measured statistically (not visually)

New additions:

* Z-score based entries fileciteturn18file13
* probability-based reversion (68-95-99 rule)
* extreme bands (1.618 levels)

Insight:

* moves beyond simple RSI → true probabilistic framework

### 12.4 VWAP / Anchored Fair Value

Concept:

* price relative to "fair value" (VWAP)

New additions:

* anchored VWAP by timeframe fileciteturn18file13
* institutional reference levels

Usage:

* mean reversion around VWAP
* trailing stop for trend strategies

### 12.5 Adaptive Volatility Bands

Concept:

* dynamic support/resistance based on volatility

New additions:

* Fibonacci-weighted volatility bands fileciteturn18file13
* equilibrium vs expansion vs extreme zones

Insight:

* replaces static levels with adaptive structure

### 12.6 Institutional / Smart Money Concepts (SMC)

Concept:

* markets driven by liquidity and institutional order flow

New additions:

* order blocks
* fair value gaps
* liquidity sweeps fileciteturn18file11

Insight:

* focuses on why price moves, not just indicators

### 12.7 Adaptive Trend Detection

Concept:

* dynamically find best trend structure

New additions:

* regression-based channel selection fileciteturn18file10
* multi-period evaluation

Insight:

* avoids fixed lookback bias

---

## 13. Updated System Insight

Most blogs repeat the same surface ideas.

Real unique additions identified:

* statistical framing (Z-score, probability)
* structured execution (multi TP / SL)
* adaptive structures (VWAP, channels, volatility bands)
* institutional lens (SMC)

Everything else is:

* variations of mean reversion
* variations of momentum

---

## 14. Next Evolution Direction

System should evolve toward:

* probabilistic decision making (not threshold-based)
* adaptive structures (VWAP, volatility bands)
* structured execution (multi TP/SL)
* regime-aware + structure-aware hybrid system

This document will continue to evolve as new concepts are identified.

---

## 15. Practical Next Step

The immediate next step for this project is not to add new indicators.

It is to add a structure-aware regime layer that can control when existing strategy components are allowed to act.

Why this comes first:

* the current system still drifts toward buy-and-hold behavior when DCA keeps accumulating
* swing activity is too sparse to offset that drift
* portfolio behavior is being driven more by exposure accumulation than by regime-aware decision making

### 15.1 Structure-Aware Regime Model

The next regime layer should be based on market structure rather than indicator thresholds alone.

Target sequence:

* bullish:
  * `HH -> HL -> HH -> HL`
* weakening_bull:
  * break of prior `HL`
* bearish_confirmed:
  * lower high after weakness
  * then break of prior `LL`
* sideways:
  * range high / range low
  * avoid interpreting every internal swing as trend structure

System meaning:

* break of `HL` = trend weakening
* break of `LL` = bearish confirmation
* no clean continuation = range / no trend

### 15.2 Concrete Regime Permissions

Bullish:

* allow DCA
* allow swing entries
* allow normal swing exits

Weakening Bull:

* reduce or pause DCA
* allow only selective swing entries
* tighten risk

Bearish Confirmed:

* disable DCA
* disable new long swing entries
* allow only exits, de-risking, and defensive actions

Sideways:

* allow controlled mean reversion
* keep momentum swing selective or disabled
* treat as a range, not as trend continuation

### 15.3 Ordered Implementation Plan

Phase 1:

* add swing-point extraction
* classify structure states
* transition regime from structure, with indicators as confirmation

Phase 2:

* gate DCA by regime
* add max BTC allocation cap
* add DCA pause logic tied to structure and exposure

Phase 3:

* add portfolio-level de-risking
* add exposure caps
* add partial sell / rebalance rules

Phase 4:

* revisit swing strictness only after the above
* verify swing contributes incremental PnL beyond DCA

This order matters more than adding more research concepts at this stage.

### 15.4 Current Implementation Status

The first pass of this direction is now live:

* structure-aware regime classification exists
* `bearish` blocks new DCA buys by default
* `weakening_bull` reduces DCA order size instead of keeping blind full-size accumulation
* BTC allocation cap is enforced before DCA adds more exposure
* DCA can now emit partial rebalance sells to reduce base BTC exposure when the portfolio is too BTC-heavy for `weakening_bull` or `bearish`
* new long swing entries are now blocked by default outside `bullish`, while existing swing positions can still exit

This is still an early control layer, not a full portfolio-intent engine.

Still missing:

* broader portfolio-level de-risking beyond DCA inventory
* explicit non-DCA rebalance rules
* richer swing permissions than the current default block/allow model
