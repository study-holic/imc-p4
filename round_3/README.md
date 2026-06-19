# Round 3 — Options Pricing & Backtester Reliability

## Overview
Round 3 was a step change in complexity: a dozen products arrived at once, comprising a small set of underlyings and a ladder of option-style vouchers spanning deep in-the-money to far out-of-the-money. The market now demanded derivatives thinking, implied volatility, a volatility smile, and the relationship between each voucher and its underlying, alongside the market-making from earlier rounds. It also became the round where I learned the most about how far my backtester could be trusted.

## Exploratory Data Analysis
This round used the broadest EDA toolkit of the competition. For the underlyings I examined tick-change autocorrelation and rolling level statistics to test whether they mean-reverted or trended. For the vouchers I computed rolling implied-volatility series per strike, looked at how the smile shape evolved across the provided days, and studied per-strike IV drift. At the microstructure level I analysed level-1 and level-2 spread and volume-imbalance distributions and quantised order-book skew, measuring the significance of short-horizon forward moves conditioned on book state. I checked inter-product correlations for pair-trading potential and found them too unstable to lean on. Crucially, I adopted an explicit holdout, fit on the earlier days, test on a held-out day, so I could see overfitting before it cost me live. Each of these analyses fed strategy-archetype selection rather than a single signal.

## Strategy Approach
The design was modular per product: delta-1 market-making on the underlyings, implied-volatility market-making with a smile fit plus a mean-reversion overlay on the near-the-money vouchers, and a more robust rolling-IV approach on the wings. The unifying principle was matching each instrument to the archetype its data supported rather than imposing one model across the board.

## Hyperparameter Tuning
Tuning was a manual grid run across a long sequence of live-submission experiments, with the backtester used only to rank candidates relatively. Every candidate had to clear two gates before shipping: a holdout-day PnL check and a multi-seed noise-stress test, a discipline that mattered far more than any single parameter value.

## What I Learned
- The backtester systematically over-estimated PnL, and dramatically so for aggressive liquidity-taking; calibrating sim-to-live gates became non-negotiable.
- A statistically significant signal isn't the same as a tradable edge once you include execution costs and adverse selection.
- Negative tick-autocorrelation can coexist with sustained drift, a reminder to verify the exact form of "mean reversion" before trading it.

## Results
- Algorithm PnL: -403 (rank 2,509)
- Manual PnL: +75,241 (rank 233)
- Cumulative position: 2,156th
