# Round 1

## Products

- `ASH_COATED_OSMIUM`
- `INTARIAN_PEPPER_ROOT`

Position limit: 80 per product.

## Approach

Per-product market making. One product is treated as a stable asset and quoted around a fixed fair value with symmetric inventory-clearing logic; the other is treated as a directional product and the algorithm builds and holds a position rather than market-make.

The trading loop is a single `Trader.run` that dispatches by product symbol. There is no shared persistent state in this round — each tick is handled from the order book and current position alone.

## Results

| Metric         | Value          |
| -------------- | -------------- |
| Algorithm PnL  | +96,942 (rank 1231) |
| Manual PnL     | +85,000 (rank 25)   |
| Round position | 1375th         |

## Reflection

Round 1 was a confidence check on the submission pipeline as much as a strategy round — verifying that the `Trader` interface, position limits and order placement worked end-to-end. The manual trade scored well (top 25 globally) because the brief admitted a clean optimisation. Treating each product with the framework that best matches its statistical character (rather than forcing one model across both) carried over into every later round.
