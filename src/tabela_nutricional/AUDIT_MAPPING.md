# Audit mapping (pre-refactor)

## Uses of round() / format-based rounding (non half-up)
- `calculator.py` line 83-84: `round(value)` in `_round_value()` (bankers).
- `calculator.py` line 81: `f"{value:.{r['decimal']}f}"` (bankers via float format).
- `calculator.py` line 156: `round(percent)` for %VD.
- `calculator.py` line 180: `round(...)` for energy.

## Mixing Annex III (rounding) vs Annex IV (significance)
- Single dict `RULES` holds both `threshold` (Anexo IV) and `rounding` (Anexo III).
- `_round_value_numeric` applies threshold before rounding (correct order but mixed concern).
- `_format_result_set` applies significance then rounding in one pass.

## Gaps vs RDC 429 / IN 75
- No 100ml / unit_base; aggregation assumes 100g only.
- No food_form (solid/liquid), recipe_mode (as_sold/as_prepared).
- Anexo IV: only trans conditional (saturated+trans); no conventional/supplement/prepared split.
- Anexo XXII: no polyols, ethanol, organic_acids, polydextrose in energy.
- Output lacks: unit, is_insignificant, vd_display "**", notes.
- No portion_size validation vs Anexo V.
