# Round 4

## Overview
Round 4 carried forward the same product family as Round 3 and is, in retrospect, the round I learned the most from, not because it went well, but because it exposed the failure modes of my own process. The algorithm itself held up and scored positively, but the round total went negative on the back of a costly manual-trading decision, and the algorithm research showed how easily a well-fitted model becomes an over-fitted one.

## Exploratory Data Analysis
The analysis here was the most ambitious of the competition. I fitted autoregressive and mean-reversion models per product, estimating half-lives and running unit-root tests to judge how reliably each product reverted. I profiled counterparty behaviour from the named-trade data to characterise the flow I was trading against, and built a flow-toxicity view by correlating order-book imbalance with short-horizon forward returns. For the vouchers I compared empirical hedge ratios against theoretical ones and examined the smile's shape and stability across sessions. The depth of this work was double-edged: it produced genuine insight, but it also tempted me toward models with more moving parts than the live regime would reward, which became the round's central lesson.

## Strategy Approach
The algorithm combined Black-Scholes-based options pricing with a smile treatment, mean reversion, market-making, and microstructure-aware fair values, with counterparty profiling wired in. Strategies stayed modular per product. The weakness wasn't any single archetype but the accumulated complexity, and an over-reliance on parameters fitted to the previous round's regime.

## Hyperparameter Tuning
This round introduced formal automated tuning: Optuna with a TPE sampler searching over categories of spread, inventory, signal-window, threshold and fair-value-anchor parameters, on the order of 50 to 200 trials per study, with a holdout-day check used as the stopping criterion. The objective tracked risk-adjusted backtester PnL, but the tuned values still had to survive live submission, and the round was a sharp reminder of why that caveat exists.

## What I Learned
- Parameters tuned to one regime can fail silently when the regime shifts; an anchor that fits one round isn't a constant.
- Complexity has a cost; more components meant more hidden assumptions and a wider sim-to-live gap.
- The diagnosis from this round, over-engineering, regime sensitivity, and the need for adaptive rather than hardcoded fair values, directly informed the Round 5 rebuild.

## Results
- Algorithm PnL: +42,475 (rank 930)
- Manual PnL: -143,633 (rank 1,448)
- Cumulative position: 3,224th
