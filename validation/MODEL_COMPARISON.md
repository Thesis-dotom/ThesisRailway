# Current-snapshot model check

Snapshot: 20261028T190809-9403 (2026-10-28T19:08:09.940396+00:00).

This is a comparison of scoring rules on the current dataset, plus a small weight-sensitivity exercise. It is not a historical performance test, an optimized portfolio or evidence that one model earns better returns.

- Universe: 109; reports returned: 109.
- Model 3 complete pairs: 104; companies with at least one score: 107.
- Model 2 complete pairs when applied to these same current reports: 99.
- Newly visible usable companies previously withheld by model 2: FLR, NEOG, AZTA, BRKR, COHU, ABT, LOW, APD, DOW.
- Rank correlation among the 95 companies with both models complete: 0.205.

Model 2 uses its original provider ratios, growth inputs, analyst targets and momentum. Model 3 uses aligned annual data and peer medians. Both are evaluated on the raw fields collected in this refresh; the definitions intentionally differ. This comparison isolates the current scoring rules, not historical investment returns.

## Factor sensitivity

Each factor weight is independently increased or decreased by 20%, then that score group is normalized back to 100. Other factors are held fixed. The screen thresholds remain unchanged. Rank movement is measured only within companies with both complete scores.

| Factor | Weight multiplier | Top 10 retained | Largest rank move | Screen entries / exits |
| --- | --- | --- | --- | --- |
| Operating return on capital | 0.8 | 10/10 | 4 | None / None |
| Operating return on capital | 1.2 | 10/10 | 4 | None / None |
| Three-year operating margin | 0.8 | 10/10 | 5 | None / None |
| Three-year operating margin | 1.2 | 10/10 | 2 | None / None |
| Three-year free-cash-flow margin | 0.8 | 10/10 | 4 | None / None |
| Three-year free-cash-flow margin | 1.2 | 10/10 | 3 | None / None |
| Cash-flow consistency | 0.8 | 10/10 | 1 | None / None |
| Cash-flow consistency | 1.2 | 10/10 | 3 | None / None |
| Net debt / EBITDA | 0.8 | 10/10 | 5 | None / None |
| Net debt / EBITDA | 1.2 | 10/10 | 2 | None / None |
| Annualized revenue growth | 0.8 | 10/10 | 4 | None / None |
| Annualized revenue growth | 1.2 | 10/10 | 2 | None / None |
| Annualized diluted EPS growth | 0.8 | 10/10 | 3 | None / None |
| Annualized diluted EPS growth | 1.2 | 10/10 | 6 | None / None |
| Annual earnings yield | 0.8 | 10/10 | 3 | None / None |
| Annual earnings yield | 1.2 | 10/10 | 2 | None / None |
| Annual free-cash-flow yield | 0.8 | 10/10 | 5 | None / None |
| Annual free-cash-flow yield | 1.2 | 10/10 | 6 | None / None |
| Annual EBITDA / enterprise value | 0.8 | 10/10 | 3 | None / None |
| Annual EBITDA / enterprise value | 1.2 | 10/10 | 5 | None / None |

## Before claiming investment performance

Keep dated weekly snapshots and model versions for forward observation. For a valid historical study, obtain point-in-time filings and prices, include delisted securities and a contemporaneous universe, set a fixed rebalance rule and transaction costs, select an appropriate benchmark, and reserve an untouched out-of-sample period. Do not fill old periods with today’s revised fundamentals. No historical dataset meeting those conditions is included here.
