## 5.2 Optimization objective

After applying all valid directive adjustments, minimize the total cost of grid electricity over the 24-hour horizon:

```text
total_cost_bdt = SUM(grid_kwh[h] * tariff_bdt_per_kwh[h]) for h = 0..23
```

Lower cost is better, but a low-cost schedule is invalid if it breaks any energy, battery, or operator-directive rule.

## 5.3 How directives change the math

| Directive | Deterministic effect used by the optimizer |
| :--- | :--- |
| `solar_reduction` | `effective_solar[h] = original_solar[h] * factor` for each listed hour. |
| `minimum_battery_reserve` | `battery_energy_after_kwh[h] >= max(base minimum_energy_kwh, directive minimum_energy_kwh)` for each listed hour. |
| `no_charge_window` | battery charge amount = 0 in the listed hours. |
| `no_discharge_window` | battery discharge amount = 0 in the listed hours. |
| `max_grid_window` | `grid_kwh[h] <= max_grid_kwh` in the listed hours. |
| `no_op` | No change to the optimization model. |