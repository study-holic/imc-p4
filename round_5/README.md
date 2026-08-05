# Round 5

## Overview
Round 5 introduced the widest market of the competition at us: fifty products organised into ten families of related variants. After Round 4 showed me exactly what over-engineering costs, I rebuilt my whole approach around one principle, something simpler and more disciplined that I could actually trust to behave the same in live as it did in simulation. It ended up being my strongest algorithmic result of the competition.

## Exploratory Data Analysis
With fifty products on the table, the first question was structural: did these families actually support a basket or relative-value trade? I built within-family and cross-family correlation matrices on tick changes, looking for stable ratios that would justify a multi-leg strategy. They weren't there. Cross-correlations were basically zero or too unstable to build anything on. So I ranked every product by one-tick autocorrelation and rolling volatility instead, to work out which were calm enough to safely make markets on and which needed more caution. The most important finding from this round's EDA was actually a negative one: the data didn't support the complex composite strategy the product structure seemed to be inviting, and that's what freed me up to commit to something simpler with confidence instead of just hoping it would work.

## Strategy Approach
Instead of building ten bespoke basket strategies, I applied one uniform market-making template across all fifty products: a smoothed fair-value anchor, position-aware skew that automatically pulls inventory back toward neutral, and spread-aware passive quoting with takes reserved for clearly favourable prices only. Per-product behaviour came out of each product's own data running through the same template, not from special-casing individual products. The modularity from earlier rounds turned into uniformity here, which was the right call for a market this broad and this unfamiliar.

## Hyperparameter Tuning
Deliberately, no automated search this round. Just a small, hardcoded, well-understood set of parameters chosen for robustness rather than the highest possible backtester PnL. After Round 4, rejecting tuning complexity was itself the actual design decision. Fewer knobs meant fewer ways to overfit and a smaller gap between sim and live.

## What I Learned
- A simpler strategy with failure modes I understood beat a clever one with hidden assumptions, and it wasn't close this round.
- A negative EDA result (no basket edge here) is still a genuinely strong result. It rules out a whole class of fragile strategy before it has the chance to lose you money.
- Discipline applied uniformly scaled cleanly across fifty products in a way bespoke complexity never would have.

## Results
- Algorithm PnL: +186,005 (rank 69 of ~18,803, top 0.4%)
- Manual PnL: +27,649 (rank 1,600)
- Cumulative position: 1,190th
