# Round 1

## Overview
The opening round introduced two products with sharply different personalities: one stable and peg-like, the other persistently directional. With only a few days of order-book data per product, the real work was less about finding a clever edge and more about building the machinery to find edges reliably across the rounds to come.

## Exploratory Data Analysis
I started by reconstructing mid-price series from the level-1 and level-2 order book and computing rolling statistics, moving mean and standard deviation, to see how tightly each product traded around a central value. For the directional product I fitted simple trend estimates and checked day-by-day consistency, to judge whether the movement was a stable feature or just an artefact of a single session. I volume-filtered the book to separate genuine market-maker quotes from thin, noisy levels, which mattered for computing a fair value that wasn't dragged around by one-lot orders. Spread and depth distributions told me how much room there was to quote passively without being immediately adversely selected. The work was deliberately descriptive; the goal was to classify each product into a market archetype, stable versus trending, so the right strategy template could be matched to it, rather than to extract one precise tradable threshold. This informed the choice of strategy archetype rather than producing a signal in itself.

## Strategy Approach
Each product was handled by a modular strategy chosen from its archetype. The stable product used a market-making framework with an explicit fair value and inventory-aware quoting, so accumulated position was worked back toward neutral rather than left to run. The directional product used an accumulation approach that leaned into the observed drift. I kept strategies separate per product rather than forcing them into one monolithic rule set, a pattern that held for the rest of the competition.

## Hyperparameter Tuning
Tuning at this stage was manual: I compared candidate settings on the provided days and sanity-checked them for stability rather than optimising by search. Formal automated tuning came later, once the iteration loop and backtester were mature enough to justify it.

## What I Learned
- Most of the first round's value was infrastructural; a clean iteration loop pays compounding dividends across later rounds.
- Matching a strategy archetype to an observed market archetype beat trying to make one rule fit both products.
- Simpler quoting logic with understood failure modes was easier to trust than added complexity.

## Results
- Algorithm PnL: +96,942 (rank 1,231 of ~18,803)
- Manual PnL: +85,000 (rank 25)
- Cumulative position: 1,375th
