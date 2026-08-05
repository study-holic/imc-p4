# Round 1

## Overview
Two products, two totally different personalities: one stable and peg-like, the other persistently directional. With only a few days of order-book data per product, this round was less about finding some clever edge and more about building the machinery I'd need to find edges reliably for the rest of the competition.

## Exploratory Data Analysis
First step was reconstructing mid-price series from the level-1 and level-2 order book, then rolling stats (moving mean and standard deviation) to see how tightly each product actually traded around a central value. For the directional product I fitted simple trend estimates and checked whether the movement held day to day, or whether it was just something that happened to show up in one session. I volume-filtered the book too, to separate genuine market-maker quotes from thin, noisy levels, since that mattered for getting a fair value that wasn't getting yanked around by one-lot orders. Spread and depth distributions told me how much room I had to quote passively without getting picked off immediately. All of this was deliberately descriptive rather than a search for one precise threshold: the goal was just to work out which archetype each product belonged to, stable or trending, so I could match the right strategy template to it.

## Strategy Approach
Each product got a strategy pulled from its archetype. The stable product ran a market-making setup with an explicit fair value and inventory-aware quoting, so any position I built up got worked back toward neutral instead of left to drift. The directional product used an accumulation approach that leaned into the drift I'd seen in the data. I kept the two strategies fully separate rather than trying to force one rule set to cover both, which ended up being the pattern for the rest of the competition too.

## Hyperparameter Tuning
Everything here was manual: comparing candidate settings across the days I had and checking they held up rather than running any kind of search. Proper automated tuning came later, once the iteration loop and backtester were solid enough to actually justify it.

## What I Learned
- Most of the value in round one was infrastructural. A clean iteration loop pays off across every round that comes after it.
- Matching a strategy archetype to what the market was actually doing beat trying to make one rule fit both products.
- Simpler quoting logic with failure modes I understood was easier to trust than adding complexity for its own sake.

## Results
- Algorithm PnL: +96,942 (rank 1,231 of ~18,803)
- Manual PnL: +85,000 (rank 25)
- Cumulative position: 1,375th
