# Round 2

## Overview
Same two products as Round 1, but more data, so the focus shifted from figuring things out to actually refining what I had. The broad picture hadn't changed, still one peg-like product and one directional one, but this was the round where I first properly ran into the gap between what the backtester promised and what the live market actually paid.

## Exploratory Data Analysis
The most useful work here was looking backward rather than forward. I pulled the execution logs from Round 1 and measured forward PnL by the price level each fill happened at, basically asking: when I traded here, what happened next? That surfaced adverse selection, certain passive fills were reliably followed by a move against me, meaning I was getting picked off at specific levels. I also ran day-by-day comparisons of each candidate version against live results, and re-checked the directional product's drift to make sure it still held in the new session. I went back over spread and order-book imbalance too, to see if my quoting needed to adapt. Same as Round 1, I kept conclusions at the level of "this tells me how to skew passive quoting" rather than pulling out one specific rule. This is what pointed me toward an inventory-aware quoting refinement.

## Strategy Approach
On the peg side I extended the plain market-making setup into inventory-skewed quoting, where the fair value I quote around shifts with my current position so I'm less likely to keep piling up on one side. It's an inventory-management idea from the Avellaneda-Stoikov family. I left the directional product's approach mostly alone since it was already performing close to its ceiling. Both strategies stayed modular and per-product, same as before.

## Hyperparameter Tuning
Still manual, but more disciplined now because live feedback was actually informing it. I compared candidate changes against the previous live submission rather than trusting backtester PnL on its own, since the two were already clearly diverging by this point.

## What I Learned
- The backtester made complex changes look better than they actually were. Live results were the only real ground truth, and I started treating them that way from here on.
- A theoretically nicer model didn't reliably beat a simpler, more targeted fix once it hit live conditions. The clever bit added surprisingly little on top of the basics.
- Adding complexity without checking it against live was what cost me rank this round. That's the lesson that set up the gating discipline I used later on.

## Results
- Algorithm PnL: +76,850 (rank 3,242)
- Manual PnL: +24,233 (rank 736)
- Cumulative position: 3,241st
