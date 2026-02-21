# Legacy — Original JavaScript Implementation

This folder contains the original frontend and calculator implemented in JavaScript, kept for reference.

- **anvisaCalculator.js** — ANVISA nutritional calculator (client-side). Replaced by Python `tabela_nutricional.calculator`.
- **script.js** — Standalone app logic (wizard + UI) using `AnvisaCalculator.calculate()` in the browser.
- **index.html** — Standalone page that loads the above scripts (no backend).
- **styles.css** — Styles for the standalone page.

The current application uses the Flask backend (`app.py`) with the Python calculator and `static/app.js` (API-based frontend).
