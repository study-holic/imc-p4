```markdown
# IMC Prosperity 4

IMC Prosperity is a 15-day algorithmic and manual trading competition run by IMC Trading, a global proprietary trading firm. Over five rounds, each team writes a Python algorithm that trades a simulated market against bots, and separately solves a one-shot manual decision problem under uncertainty. Every round introduces new products and market dynamics, and the leaderboard is recomputed cumulatively, so a strong finish only counts if the algorithm holds up across all five. I competed solo, against teams from top universities worldwide.

## Final Results
- **1,190th overall out of 18,803 teams** (top 6.3%)
- **318th globally in algorithmic trading** (top 1.7%)
- **128th in the UK**
- **69th globally in the Round 5 algorithm** (top 0.4%)
- Competing solo against teams from **1,549 universities across 117 countries**

## Round-by-Round Performance

| Round | Algo PnL | Algo rank | Manual PnL | Manual rank | Cumulative position |
| ----- | -------: | --------: | ---------: | ----------: | ------------------: |
| 1     | +96,942  | 1,231     | +85,000    | 25          | 1,375               |
| 2     | +76,850  | 3,242     | +24,233    | 736         | 3,241               |
| 3     | -403     | 2,509     | +75,241    | 233         | 2,156               |
| 4     | +42,475  | 930       | -143,633   | 1,448       | 3,224               |
| 5     | +186,005 | 69        | +27,649    | 1,600       | 1,190               |

Full breakdown in [`docs/results.md`](docs/results.md).

## Methodology

### Research Workflow
Each round followed the same loop: exploratory analysis of the provided order-book CSVs, a strategy hypothesis matched to the observed market archetype, implementation against the IMC datamodel API, validation on a custom backtester, live submission, then a diagnosis of the delta between simulated and live results that fed the next iteration. I treated writeups from previous Prosperity competitions as first-class research inputs, mining them for which strategy families had historically transferred to live. The most valuable habit was closing the loop, never treating a backtester number as truth until it had survived the live market.

### Exploratory Data Analysis
Across rounds I used a consistent toolkit: rolling price statistics, tick-change autocorrelation, spread and volume-distribution analysis, order-book depth and imbalance, inter-product correlation matrices, volatility-regime detection, and day-by-day comparisons across the provided sessions. For derivative products this extended to implied-volatility series and volatility-smile analysis. The aim was always to classify a product into an archetype that dictated strategy, not to extract a single magic threshold. More detail in [`docs/methodology.md`](docs/methodology.md).

### Strategy Design
I built a library of modular, per-product strategies rather than one monolithic system: market-making with inventory management, mean reversion via Z-score signals on rolling windows, momentum and trend-following, options pricing with Black-Scholes and smile-aware calibration, and basket/relative-value approaches. Each product was assigned the archetype its data supported. The modularity meant a failure in one product's model was contained rather than systemic.

### Hyperparameter Tuning
Where a strategy had enough parameters to justify it, most notably the derivative-pricing round, I used Optuna with TPE sampling and a holdout-based stopping criterion, on the order of 50 to 200 trials per study, optimising risk-adjusted backtester PnL. Elsewhere, tuning was a disciplined manual grid validated by live A/B submissions. In all cases tuned values were candidates rather than answers, because the backtester's divergence from live was a known and quantified limitation.

### Versioning & Diagnostics
I maintained structured versioning across submissions, dozens of incrementally numbered variants per round, each paired with a findings note recording what changed and why. Every live submission produced a delta analysis comparing what the backtester predicted against what the market actually paid. This diagnostic loop, more than any individual strategy, was what improved my results over the competition.

## Key Methodological Lessons
- Backtester results require calibration against live; marginal improvements below the simulation noise floor aren't reliable ship signals.
- Simpler strategies with well-understood failure modes outperformed clever ones with hidden assumptions.
- Per-product strategy archetypes outperformed monolithic frameworks.
- Diagnosing the delta between simulated and live performance was more valuable than chasing absolute backtester PnL.

## Repository Structure

```
imc-prosperity-4-public/
├── README.md
├── LICENSE                  (MIT)
├── .gitignore
├── docs/
│   ├── results.md
│   └── methodology.md
├── round_1/
│   ├── algorithm.py
│   └── README.md
├── round_2/
│   ├── algorithm.py
│   └── README.md
├── round_3/
│   ├── algorithm.py
│   └── README.md
├── round_4/
│   ├── algorithm.py
│   └── README.md
└── round_5/
    ├── algorithm.py
    └── README.md
```

## What's In Here (and What Isn't)
This repository contains the algorithm I submitted for each round, a README per round, and a methodology write-up; these describe *how* I worked, in technique and lessons. The tuning rationale, the experimental log, and the reasoning for why each edge works are intentionally omitted: I'm competing again in Prosperity 5. The methodology is shareable; the playbook isn't.

## Tech Stack
- Python 3
- The IMC Prosperity datamodel API (`OrderDepth`, `TradingState`, `Order`)
- pandas, numpy for EDA
- matplotlib, seaborn for visualisation
- Optuna for hyperparameter tuning (TPE sampler, holdout-based stopping)
- A custom Rust-based backtester for rapid iteration

## About the Competition
IMC Prosperity is IMC Trading's annual 15-day algorithmic and manual trading competition, scoring algorithms against bot-populated order books on a hidden day of data. It's widely regarded as one of the closest experiences to real quant research available to students.

## License
MIT, see [`LICENSE`](LICENSE).
```
