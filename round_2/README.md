# Round 2

## Overview
Round 2 kept the same two products and added more data, so the focus shifted from discovery to refinement. The broad market picture was unchanged, one peg-like product, one directional, but the round became my first real encounter with the gap between what the backtester promised and what the live market delivered.

## Exploratory Data Analysis
The most useful analysis here was post-trade rather than pre-trade. I took the execution logs from the previous round and measured forward PnL by the price level at which each fill occurred, effectively asking, when I traded here, what happened next. This surfaced adverse selection: certain passive fills were systematically followed by unfavourable moves, meaning I was being picked off at specific levels. I also ran day-by-day comparisons of each candidate version against live results, and re-characterised the directional product's drift to confirm it held across the new session. I revisited spread and order-book imbalance distributions to see whether quoting behaviour needed to adapt. As in Round 1, I framed conclusions at the level of "this informs how passive quoting should be skewed," rather than a specific tradable rule. This investigation is what pointed me toward an inventory-aware quoting refinement.

## Strategy Approach
The peg-side strategy was extended from plain market-making toward inventory-skewed quoting, where the fair value used for quoting shifts with current position to discourage one-sided accumulation, an inventory-management idea in the Avellaneda–Stoikov family. The directional product's approach was left largely intact, since it was already performing near its ceiling. Strategies remained modular and per-product.

## Hyperparameter Tuning
Still manual, but now disciplined by live feedback: I compared candidate changes against the prior live submission rather than judging them on backtester PnL alone, because the two were already visibly diverging.

## What I Learned
- The backtester flattered complex changes; live results were the only ground truth, and I started treating them that way.
- A theoretically nicer model didn't reliably beat a simpler, well-targeted fix in live conditions; the "clever" component added little on top of the basics.
- Expanding complexity without a sim-to-live check was how the rank slipped this round; the lesson set up the gating discipline I used later.

## Results
- Algorithm PnL: +76,850 (rank 3,242)
- Manual PnL: +24,233 (rank 736)
- Cumulative position: 3,241st
