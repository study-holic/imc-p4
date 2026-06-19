# Methodology
This note expands on how I approached IMC Prosperity 4: the research process, the analytical toolkit, and the discipline that mattered more than any individual strategy. It's deliberately about technique rather than the specific edges I traded.

## The EDA toolkit
Every round started with the same question, what kind of market is this, answered with a standard set of tools, each chosen for what it reveals:

- **Rolling statistics** (mean and standard deviation over a moving window) show whether a product is stable around a level or wandering; the first cut between a market-making candidate and a directional one.
- **Autocorrelation** of tick-to-tick changes shows whether short-horizon moves reverse or persist, separating mean-reversion candidates from trend-following ones. A caution I learned the hard way: negative tick autocorrelation can coexist with a sustained drift, so you have to verify the *form* of reversion before trading it.
- **Order-book imbalance and depth** expose short-term flow pressure, and how much you can quote passively before adverse selection bites.
- **Correlation matrices** across related products test for basket or relative-value relationships, and just as importantly, rule them out when the relationships prove unstable.
- **Volatility-regime detection** flags when a product's behaviour shifts between sessions, which governs whether a fitted model can be trusted going forward.
- For derivatives, **implied-volatility series and smile analysis** turn raw voucher prices into a comparable value surface.

## Matching archetype to behaviour
The point of EDA is strategy selection. A stable, tightly-ranged product suggests market-making with inventory management. Strong, reliable short-horizon reversion suggests mean reversion on a rolling Z-score. Persistent drift suggests momentum or accumulation. A derivative trading away from its model value suggests options pricing with smile-aware calibration. Stable inter-product ratios suggest basket or relative-value trades. Crucially, I assigned these per product; a single round often ran several archetypes side by side, each kept contained so one product's failure didn't sink the others.

## The Optuna workflow
Where a strategy carried enough parameters to justify automated search, I used Optuna with TPE sampling. I organised studies by parameter *category*, spread parameters, inventory thresholds, signal windows, signal thresholds, rather than as one undifferentiated space, which kept the results interpretable. A holdout day served as both a validation set and a stopping criterion, and the objective optimised risk-adjusted PnL rather than raw return, so I wasn't rewarding fragile high-variance configurations. Tuned values were always candidates pending live confirmation, never final answers.

## The sim-to-live diagnostic
The backtester was indispensable for ranking ideas but systematically optimistic, and the most important ongoing work was quantifying that gap. After each submission I compared simulated against live PnL, per product where possible, to learn which strategy types transferred faithfully and which degraded. The pattern held up consistently: passive, market-making-style strategies transferred far better than aggressive liquidity-taking, whose simulated profits were largely illusory. That led to two hard gates for any candidate before it shipped: a holdout-day PnL check and a multi-seed noise-stress test, with marginal gains below the noise floor treated as no signal at all.
