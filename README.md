# India_Lead_Flow_Model — Streamlit app

> **This README is a placeholder.** Replace the contents of this file with the
> documentation doc you wanted on Tab 3 — the dashboard's Tab 3 renders this
> file as-is.

Model for quantifying flows of lead through India (WIP).

## What this app does

Implements the **v5 parallel formal/informal mass-balance chain** for lead in
India, with both formal and informal lanes running through breaking, smelting,
refining, and manufacturing. USGS-reported secondary refined lead is treated
as a one-sided floor on the formal lane (overshoot is the implied unrecorded
informal/formal-equivalent refined Pb).

## Tabs

1. **Flow diagram** — interactive system diagram (streamlit-flow-component +
   Plotly fallback), per-node detail (formula / variables / assumptions / per-
   year volumes), and a line graph of the major process steps over the fit
   window.
2. **Controls** — editable stock series, battery segments (lifetime mix),
   stock multiplier `k`, optional `τ` override, and the four formal-share
   values `φ_break_f < φ_smelt_f < φ_refine_f < φ_mfg_f`.
3. **README** — this document.

Process parameters (`β`, `γ`, and the eight `η`'s) live in the **sidebar**.

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Files

```
streamlit_app.py            entry point
app/
  state.py                  session-state + canonical chain solve
  sidebar.py                β / γ / η inputs
  controls.py               Tab 2 inputs
  diagram.py                Tab 1 flow diagram + line graph
  readme.py                 Tab 3 renderer
india_model/
  model_v5_parallel.py      the parallel chain
  model_v4.py               retirement/growth utilities (still used by v5)
  india_mass_balance_2018_2023.csv   consolidated USGS + BACI + stock series
  segment_lifetimes.csv     SLI=3 / e_rickshaw=2 / stationary=7 (USAID)
requirements.txt
.streamlit/config.toml
```

## Provenance

- USGS primary + secondary refined Pb, India, 2018–2023.
- BACI HS-6 trade data (CEPII), filtered to relevant Pb-containing HS codes,
  with per-HS Pb-content conversion factors applied upstream (built into
  `india_mass_balance_2018_2023.csv`).
- Stock series from `India_Installed` (USAID-derived, propagated to the mass-
  balance CSV).
- Process parameters (β, γ, η's, φ floors) from USAID guidance + literature.
