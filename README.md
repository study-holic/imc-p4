# IMC Prosperity 4 — Solo Competition

IMC Prosperity is a 15-day algorithmic and manual trading competition run by IMC Trading, a global proprietary trading firm. Each round combines a Python algorithm that trades a simulated market against bots, and a one-shot manual decision problem under uncertainty. I competed solo, without a team.

## Final results

- **1,190 / 18,803** teams overall (top 6.3%)
- **318 / 18,803** globally in algorithmic trading (top 1.7%)
- **128** in the United Kingdom
- **69** globally in the Round 5 algorithm (top 0.4%)
- Competing solo against teams from **1,549 universities across 117 countries**

## Round-by-round

| Round | Algo PnL    | Algo rank | Manual PnL | Manual rank | Round position |
| ----- | ----------: | --------: | ---------: | ----------: | -------------: |
| 1     | +96,942     | 1,231     | +85,000    | 25          | 1,375          |
| 2     | +76,850     | 3,242     | +24,233    | 736         | 3,241          |
| 3     | -403        | 2,509     | +75,241    | 233         | 2,156          |
| 4     | +42,475     | 930       | -143,633   | 1,448       | 3,224          |
| 5     | +186,005    | 69        | +27,649    | 1,600       | 1,190          |

Full table in [`docs/results.md`](docs/results.md).

## Repository structure

```
imc-prosperity-4-public/
├── README.md
├── LICENSE                  (MIT)
├── .gitignore
├── docs/
│   └── results.md
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

## What's in here

One algorithm per round (the version actually submitted to IMC's platform), plus a short retrospective for each round. Specific signal definitions, parameter-tuning rationale and the experimental log behind each iteration have been intentionally omitted — I am competing again in Prosperity 5 and prefer not to publish what I learned about how the IMC platform behaved.

## Tech stack

- Python 3
- The IMC Prosperity `datamodel` API (`OrderDepth`, `TradingState`, `Order`)
- A custom backtester for iteration between rounds
- Black-Scholes pricing implemented inline (no SciPy on the platform)

## About the competition

Prosperity 4 ran in April 2025. Each round opens an algorithm submission window and a separate manual-trading puzzle; algorithms are scored against bot-populated order books on a hidden day of data. The leaderboard is recomputed cumulatively after each round, so a strong finish in one round only reaches the top tiers if the algorithm holds up across all five.

## License

MIT — see [`LICENSE`](LICENSE).
