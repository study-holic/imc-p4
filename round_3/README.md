# Round 3

## Overview
Round 3 was a real step up in complexity: a dozen products showed up at once, a small set of underlyings plus a whole ladder of option-style vouchers running from deep in-the-money to far out-of-the-money. Suddenly the market wanted actual derivatives thinking, implied volatility, a volatility smile, the relationship between each voucher and its underlying, on top of the market-making I'd already been doing. This was also the round where I learned the most about exactly how far I could trust my backtester.

## Exploratory Data Analysis
This was the widest EDA toolkit I used all competition. For the underlyings I looked at tick-change autocorrelation and rolling level stats to check whether they mean-reverted or trended. For the vouchers I computed rolling implied-vol series per strike, watched how the smile shape moved across the available days, and studied per-strike IV drift. At the microstructure level I went through level-1 and level-2 spread and volume-imbalance distributions and quantised order-book skew, checking whether short-horizon forward moves were actually significant given the state of the book. I checked correlations between products for pair-trading potential too, but they were too unstable to lean on. The important bit though: I brought in a proper holdout this round, fit on the earlier days, test on a day I hadn't touched, so I could catch overfitting before it cost me live. All of this fed into which archetype I assigned each instrument, rather than producing one single tradable signal.

## Strategy Approach
Same modular, per-product design as before: delta-1 market-making on the underlyings, implied-vol market-making with a smile fit and a mean-reversion overlay on the near-the-money vouchers, and a more robust rolling-IV approach on the wings where the smile fit was shakier. The principle stayed the same throughout: match each instrument to the archetype its data actually supported, rather than forcing one model across everything.

## Hyperparameter Tuning
Manual grid search run across a long string of live-submission experiments, with the backtester only used to rank candidates against each other rather than trusted outright. Every candidate had to clear two gates before I'd ship it: a holdout-day PnL check and a multi-seed noise-stress test. That discipline mattered far more than any individual parameter value I landed on.

## What I Learned
- The backtester systematically overstated PnL, badly so for anything aggressively liquidity-taking. Calibrating sim-to-live gates stopped being optional after this round.
- A statistically significant signal isn't automatically a tradable edge once you factor in execution costs and adverse selection.
- Negative tick-autocorrelation can happily coexist with sustained drift. Good reminder to actually verify what "mean reversion" means for a given product before trading on the assumption.

## Results
- Algorithm PnL: -403 (rank 2,509)
- Manual PnL: +75,241 (rank 233)
- Cumulative position: 2,156th
