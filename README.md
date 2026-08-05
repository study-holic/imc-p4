# IMC Prosperity 4

IMC Prosperity is a 15-day algorithmic and manual trading competition run by IMC Trading, a global prop trading firm. Across five rounds you write a Python algorithm that trades against bots in a simulated market, plus a separate one-shot manual decision problem under uncertainty each round. New products and market dynamics get thrown at you every round, and the leaderboard is cumulative, so a strong last round only matters if the rest of your algorithm actually holds up. I did this solo, up against teams from top universities worldwide.

## Final Results
- **1,190th overall out of 18,803 teams** (top 6.3%)
- **318th globally in algorithmic trading** (top 1.7%)
- **128th in the UK**
- **69th globally in the Round 5 algorithm** (top 0.4%)
- Solo, against teams from **1,549 universities across 117 countries**

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
Same loop every round: dig into the order-book CSVs, form a strategy hypothesis that actually matches what the data was doing, build it against the IMC datamodel API, validate on my own backtester, submit, then work out why the live result didn't match the backtest, and feed that into the next round. I went back through writeups from previous Prosperity competitions too, trying to figure out which strategy families had actually held up live versus just looked good on paper. Honestly the single most useful habit was refusing to trust a backtester number until it had survived contact with the real market.

### Exploratory Data Analysis
Roughly the same toolkit every round: rolling price stats, tick-change autocorrelation, spread and volume distributions, order-book depth and imbalance, correlation matrices between products, volatility-regime detection, and comparing days against each other. For the options round I also pulled in implied vol series and looked at the vol smile. The point was never to fish out one magic threshold, it was to work out which archetype a product actually belonged to, since that's what decided the strategy. More detail in [`docs/methodology.md`](docs/methodology.md).

### Strategy Design
Rather than one big system trying to do everything, I built a library of per-product strategies: market-making with inventory management, mean reversion off Z-scores on rolling windows, momentum/trend-following, options pricing via Black-Scholes with smile-aware calibration, and basket/relative-value trades. Whatever archetype a product's data pointed to, that's the strategy it got. Which also meant if one product's model broke, it didn't take the rest of the system down with it.

### Hyperparameter Tuning
For anything with enough parameters to be worth it, mainly the derivatives round, I ran Optuna with TPE sampling and a holdout stopping rule, somewhere around 50-200 trials per study, optimising risk-adjusted backtester PnL. Everywhere else it was manual grid search validated by live A/B tests. Either way, tuned values were never treated as final, just candidates, because I knew the backtester diverged from live and by roughly how much.

### Versioning & Diagnostics
I kept structured versions across submissions: dozens of numbered variants per round, each with a note on what changed and why. Every live submission got a delta analysis: what the backtester said would happen versus what actually happened in the market. This loop, more than any one clever strategy, is what actually moved my results over the competition.

## Key Methodological Lessons
- Backtester results need calibrating against live; improvements smaller than the simulation noise floor aren't a real signal to ship on.
- Simple strategies with failure modes I understood beat clever ones with assumptions I hadn't fully tested.
- Per-product archetypes beat one monolithic framework.
- Working out the delta between simulated and live performance mattered more than chasing the highest backtester PnL.

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

## What's In Here
This repo has the algorithm I submitted each round, a README per round, and a methodology write-up: the how, not the why. I've deliberately left out the tuning rationale, the experiment log, and the reasoning behind why each edge actually works, because I'm competing again in Prosperity 5. Happy to share the methodology; the playbook stays mine for now.

## Tech Stack
- Python 3
- The IMC Prosperity datamodel API (`OrderDepth`, `TradingState`, `Order`)
- pandas, numpy for EDA
- matplotlib, seaborn for visualisation
- Optuna for hyperparameter tuning (TPE sampler, holdout-based stopping)
- A custom Rust-based backtester for fast iteration

## About the Competition
IMC Prosperity is IMC Trading's annual 15-day algorithmic and manual trading competition, scored against bot-populated order books on a hidden day of data. Widely considered one of the closest things to real quant research that students can get their hands on.

## License
MIT, see [`LICENSE`](LICENSE).
