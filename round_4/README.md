# Round 4

## Overview
Round 4 kept the same product family as Round 3, and looking back it's probably the round I learned the most from, not because it went well, but because it exposed the actual weak points in my process. The algorithm itself held up fine and scored positively, but the round total ended up negative because of a costly manual-trading call, and the algo research showed me exactly how easily a well-fitted model turns into an over-fitted one.

## Exploratory Data Analysis
This was the most ambitious EDA I did all competition. I fitted autoregressive and mean-reversion models per product, estimated half-lives, and ran unit-root tests to work out how reliably each product actually reverted. I profiled counterparty behaviour from the named-trade data to get a sense of what flow I was trading against, and built a flow-toxicity view by correlating order-book imbalance with short-horizon forward returns. For the vouchers I compared empirical hedge ratios against the theoretical ones and looked at how stable the smile's shape actually was across sessions. This depth of work cut both ways though: it gave me real insight, but it also pulled me toward models with more moving parts than the live regime was ever going to reward, and that ended up being the central lesson of the round.

## Strategy Approach
The algorithm combined Black-Scholes options pricing with a smile treatment, mean reversion, market-making, and microstructure-aware fair values, with counterparty profiling wired into all of it. Strategies stayed modular per product, same as before. The weakness wasn't any single archetype, it was the complexity that had built up, plus leaning too hard on parameters that had been fitted to the previous round's regime.

## Hyperparameter Tuning
This is where automated tuning properly started: Optuna with a TPE sampler searching over spread, inventory, signal-window, threshold, and fair-value-anchor parameters, somewhere around 50-200 trials per study, with a holdout-day check as the stopping rule. The objective tracked risk-adjusted backtester PnL, but the tuned values still had to survive live submission, and this round was a sharp reminder of exactly why that caveat exists.

## What I Learned
- Parameters tuned to one regime can fail quietly the moment the regime shifts. An anchor that worked for one round isn't something you can treat as a constant.
- Complexity isn't free. More components meant more hidden assumptions and a wider gap between sim and live.
- The diagnosis from this round, over-engineering, regime sensitivity, and needing adaptive rather than hardcoded fair values, is what directly shaped the Round 5 rebuild.

## Results
- Algorithm PnL: +42,475 (rank 930)
- Manual PnL: -143,633 (rank 1,448)
- Cumulative position: 3,224th
