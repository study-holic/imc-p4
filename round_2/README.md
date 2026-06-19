# Round 2

## Products

- `ASH_COATED_OSMIUM`
- `INTARIAN_PEPPER_ROOT`
- A sealed-bid market-access fee (MAF)

Position limit: 80 per product.

## Approach

Same per-product dispatch as Round 1, with asymmetric TAKE thresholds and asymmetric MAKE placement on the market-making product to reflect what the post-round-1 data showed about fill quality on each side of the book. The MAF bid was sized by reasoning about the expected distribution of competing bids relative to the algorithm's per-day uplift from winning it.

The code reads as a near-clone of Round 1 with a handful of named constants (`OSMIUM_BUY_EDGE`, `OSMIUM_SELL_EDGE`, `OSMIUM_MAKE_BID_EDGE`, `OSMIUM_MAKE_ASK_EDGE`) replacing inline magic numbers.

## Results

| Metric         | Value          |
| -------------- | -------------- |
| Algorithm PnL  | +76,850 (rank 3242) |
| Manual PnL     | +24,233 (rank 736)  |
| Round position | 3241st         |

## Reflection

The algo regressed against Round 1 in absolute and relative terms. With hindsight the rank drop was driven less by the per-side asymmetry itself and more by how much harder the playing field had become: many of the teams below me in Round 1 had now had a full round of live data to recalibrate too. The lesson I carried forward was to treat each round's leaderboard as a fresh distribution and not to read a rank drop as a strategy verdict.
