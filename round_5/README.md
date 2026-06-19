# Round 5

## Overview
Round 5 introduced the widest market of the competition: fifty products organised into ten families of related variants. After Round 4 exposed the cost of over-engineering, I rebuilt my approach from scratch around a single principle, a simpler, more disciplined framework I could trust to behave in live as it did in simulation. It produced the strongest algorithmic result of the competition.

## Exploratory Data Analysis
With fifty products the first question was structural: did the families admit a basket or relative-value trade? I built within-family and cross-family correlation matrices on tick changes, looking for stable ratios that would justify a multi-leg strategy. They weren't there; cross-correlations were near zero or too unstable to lean on. I then ranked every product by one-tick autocorrelation and rolling volatility to see which were calm enough to make markets on and which to treat cautiously. The decisive EDA finding was a negative one: the data didn't support the complex composite strategy the product structure seemed to invite, which freed me to commit to something simpler with confidence rather than hope.

## Strategy Approach
Rather than ten bespoke basket strategies, I applied one uniform market-making template across all fifty products: a smoothed fair-value anchor, position-aware skew to pull inventory back toward neutral automatically, and spread-aware passive quoting with takes reserved for clearly favourable prices. Per-product behaviour emerged from each product's own data flowing through the same template, not from per-product special-casing. The modularity of earlier rounds became uniformity here, the right call for a broad, unfamiliar surface.

## Hyperparameter Tuning
Deliberately, there was no automated search this round. Parameters were a small, hardcoded, well-understood set chosen for robustness rather than peak backtester PnL. After Round 4, rejecting tuning complexity was itself the design decision; fewer knobs meant fewer ways to overfit and a smaller sim-to-live gap.

## What I Learned
- A simpler strategy with understood failure modes outperformed a clever one with hidden assumptions, decisively, this round.
- A negative EDA result (no basket edge) is still a strong result: it rules out a whole class of fragile strategy before it can lose money.
- Discipline applied uniformly scaled cleanly to fifty products where bespoke complexity wouldn't have.

## Results
- Algorithm PnL: +186,005 (rank 69 of ~18,803, top 0.4%)
- Manual PnL: +27,649 (rank 1,600)
- Cumulative position: 1,190th
