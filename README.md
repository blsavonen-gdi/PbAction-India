# India Lead Mass-Balance Model
### Model Overview & Technical README

**A parallel formal/informal accounting of lead flows through India's lead-acid battery economy, 2018–2023**

*Draft — proof of concept · Prepared for external technical review*

> This is an early-stage model built on publicly available data and literature-derived assumptions. Several key parameters are first approximations intended to be replaced with field-collected data. The model is structured so that better inputs can be substituted without redesign; identifying which assumptions most require field validation is one of its central purposes.

---

## 1. Purpose and scope

This document describes a country-level mass-balance model of lead flows through India's lead-acid battery (LAB) economy, covering the years 2018–2023. The model's purpose is **market-structure characterization**: understanding the scale of formal versus informal processing, identifying where unverified lead enters the chain, and testing whether domestic production reconciles with reported trade and refining statistics. It is *not* intended to produce precise tonnage estimates. Its outputs are best read as ranges and structural diagnostics rather than point figures.

The model traces lead around a closed loop. Batteries are installed into an in-service stock; the stock retires over time according to an effective battery lifetime; retired batteries are collected and processed back into refined lead through four sequential stages; and refined lead is manufactured into new batteries, which return to the stock. At each processing stage the model runs two parallel pathways — a **formal** (regulated, higher-recovery) lane and an **informal** (unregulated, lower-recovery) lane — because the central policy question is what fraction of India's lead moves through channels that cannot be verified safe.

All quantities are expressed in tonnes of contained lead per year. Trade data are drawn from BACI bilateral statistics; refined and primary production from USGS; and the installed-stock series is constructed bottom-up from vehicle-fleet data. The model is calibrated over a smoothed window (a three-year centred rolling mean on the 2018–2023 series) to reduce year-to-year reporting noise.

---

## 2. The processing chain

### 2.1 Structure

Lead flows through four sequential stages — **breaking, smelting, refining, manufacturing** — each split into a formal and an informal lane. The loop is closed by retirement (the stock returning as collected scrap) and installation (manufactured batteries entering the stock). See the diagram in Tab 1 or `India_Parallel_Formal_Informal_Diagram.pdf`.

At each stage, a formal share φ governs the fraction of that stage's domestically-sourced throughput routed through the formal lane, drawing from the combined output of both upstream lanes. Because the formal share rises down the chain, the formal lane at each stage draws more material than the previous formal stage produced; that excess is informal material *sold into* the formal sector, captured as an implied crossover rather than a free parameter. This mirrors documented practice in which informal smelters sell crude lead to formal refiners.

> **DECISION — Formal share rises monotonically down the chain.** We impose the ordering φ_break < φ_smelt < φ_refine < φ_mfg < 1. Informal processing is assumed to dominate at the dirty, low-capital end (breaking) and to diminish but never vanish toward the capital-intensive end (manufacturing). No stage is ever fully formal.

> **DECISION — External trade is formal-only.** Imports and exports of used batteries, scrap, crude lead, feed materials, and finished batteries are assumed to move through legal customs channels and therefore enter the *formal* lane exclusively. The informal lane is purely domestic. Primary (mined) lead is likewise formal.

### 2.2 Equations

**Retirement and collection.** The stock growth rate `g` is fitted by log-linear regression on the installed-stock series. The retirement rate `r` follows the growth-corrected form, and collected lead is the collection rate γ applied to retirement:

```
r = g / (e^(gτ) − 1)
RETIRE(t) = k · S(t) · r
C(t) = γ · RETIRE(t)
```

Here `S(t)` is the installed stock, `τ` the effective lifetime, and `k` a stock-scaling factor (default 1.0). Collection is a single shared pool; the formal/informal split occurs at breaking.

**Breaking.** With `T_u` the net (import minus export) used-battery trade:

```
b_F_in = φ_b · C + T_u                b_I_in = (1 − φ_b) · C
b_F_out = δ · η_bF · b_F_in           b_I_out = δ · η_bI · b_I_in
```

**Smelting.** The domestic scrap pool `P_s = b_F_out + b_I_out` is split by φ_s; net scrap trade `T_s` enters the formal lane. Outputs are crude lead:

```
s_F_in = φ_s · P_s + T_s              s_I_in = (1 − φ_s) · P_s
s_F_out = η_sF · s_F_in               s_I_out = η_sI · s_I_in
```

**Refining.** The crude pool `P_r = s_F_out + s_I_out` is split by φ_r; net crude trade `T_c` (HS 780199) enters the formal lane. The formal refined output `R_F` is the quantity anchored to USGS:

```
r_F_in = φ_r · P_r + T_c              r_I_in = (1 − φ_r) · P_r
R_F = η_rF · r_F_in                   R_I = η_rI · r_I_in
```

**Manufacturing.** The refined pool `P_m = R_F + R_I` is split by φ_m; primary lead `M_p` and net feed trade `T_f` enter the formal lane. The battery share β applies to the refined-feed branch; battery parts `G` (HS 850790) are battery-committed and bypass β:

```
m_F_in = φ_m · P_m + M_p + T_f         m_I_in = (1 − φ_m) · P_m
MFG_F = β · η_mF · m_F_in + η_mF · G_+ MFG_I = β · η_mI · m_I_in
```

**Installation.** Both lanes' output plus net finished-battery trade `T_b` give implied installation, compared against stock-derived demand:

```
INSTALL_impl = MFG_F + MFG_I + T_b
INSTALL_tgt  = ΔS + RETIRE
```

**Implied crossovers.** The informal-origin material drawn into the formal lane at each downstream boundary is:

```
X_s = φ_s · P_s − b_F_out
X_r = φ_r · P_r − s_F_out
X_m = φ_m · P_m − R_F
```

A positive value is informal material sold up into the formal sector.

> **OPEN — Crossover sign conventions.** A *negative* `X_s` or `X_r` means the formal lane cannot supply its own share even after the upstream split — a sign that the φ ordering is locally infeasible at that boundary, which the model flags. At manufacturing, `X_m` may be negative for a benign reason: large primary and feed inflows (`M_p + T_f`) can mean the formal lane does not need all formal-refined output. The manufacturing crossover is therefore reported as informational only.

### 2.3 Treatment of specific trade codes

> **DECISION — HS code handling at manufacturing.** Battery parts (HS 850790) are battery-committed and routed to formal manufacturing with the manufacturing efficiency but *outside* the battery-share β (they are already destined for batteries, so the share discount does not apply). Lead oxides (HS 282410 / 282490) remain in the feed pool and *are* subject to β (litharge has genuine non-battery uses). Finished batteries (HS 850710 / 850720) skip manufacturing entirely and add directly to installation.

---

## 3. Parameters

| Parameter | Symbol | Default | Basis / status |
|---|---|---|---|
| Battery share of refined lead | β | 0.86 | Global-average share of refined lead consumed by the LAB sector; India-specific value a refinement target |
| Total collection rate | γ | 0.98 | Literature (total, formal + informal); held fixed |
| Stock-scaling factor | k | 1.0 | Identity; diagnostic lever |
| Effective lifetime | τ_eff | 3.68 yr | Stock-weighted harmonic mean of segment lifetimes; field-derated |
| Formal shares | φ_{b,s,r,m} | 0.70 / 0.80 / 0.90 / 0.95 | Informed defaults, ordered; underdetermined (§5) |
| Formal efficiencies | η_·F | 0.95 / 0.97 / 0.99 / 0.98 | Literature / engineering; held fixed |
| Informal efficiencies | η_·I | 0.70 / 0.60 / 0.95 / 0.95 | Literature + field inference; informal manufacturing least certain |
| Breaking pre-factor | δ | 0.95 | Recovery at breaking; held fixed |

Efficiency rows list **break / smelt / refine / mfg** in order.

Two parameters — the battery share β and the effective lifetime τ — carry most of the model's sensitivity and are the roughest first approximations.

The battery share **β = 0.86** is the global-average battery share of refined-lead consumption. India-specific estimates have been lower; a lower β reduces manufacturing output and widens the installation gap, so this is a priority for field refinement. The effective lifetime **τ_eff = 3.68 years** is computed by the same lifetime-weighted harmonic-mean method used in earlier versions of the model, but with shorter, field-derated per-segment life expectancies reflecting India's hot-climate operating conditions (a lead-acid battery's service life falls sharply with sustained high temperature). Both are defensible first approximations and both are explicit targets for the proposed field work.

> **DECISION — Effective lifetime from segment composition.** τ_eff is the stock-weighted harmonic mean of per-segment lifetimes. The harmonic form is required because retirement scales with the reciprocal of lifetime; short-lived segments (e.g. e-rickshaw traction batteries) therefore dominate the retirement flow out of proportion to their share of installed stock.

---

## 4. Anchors and residuals

The model is disciplined by two independent external anchors. They are **never combined into a single fit score**; each is reported separately, because they constrain different parts of the chain and can move in opposite directions.

### 4.1 The USGS refining floor (one-sided)

> **DECISION — USGS anchors formal refined output as a one-sided floor.** USGS captures *formally reported* secondary refined production. The chain estimates total formal-equivalent output. Because informal refining is not captured in official statistics, the chain is expected to *meet or exceed* USGS: a shortfall below USGS is a failure; an overshoot above it is expected and is reported separately as the implied unrecorded refined lead.

With `U` the USGS secondary figure and sums taken over the fit window:

```
shortfall_refine = max(0, ΣU − ΣR_F) / ΣU      (penalized, target ≤ 5%)
overshoot_refine = max(0, ΣR_F − ΣU) / ΣU      (reported, not penalized)
```

### 4.2 The installation balance (two-sided)

Installation is anchored two-sided against stock-derived demand:

```
res_install = (Σ INSTALL_impl − Σ INSTALL_tgt) / Σ INSTALL_tgt
```

### 4.3 Indicators

The model surfaces three indicators that can co-occur and should be read together:

- **Install-ceiling exceeded** — installation demand exceeds what the chain can supply even at full formality; signals that the stock is high relative to chain supply at the current (k, τ).
- **Refine overshoot present** — formal refined output exceeds USGS; expected under the floor framing, and its magnitude is the implied unrecorded (informal-but-formal-equivalent) refined lead.
- **Crossover infeasibility** — a negative implied crossover at smelting or refining; signals the formal-share ordering is locally inconsistent.

At the current defaults the model sits close to both anchors: installation within roughly 8% and the refine floor satisfied. This proximity is conditional on the rough β and τ values above and on the constructed stock series; under alternative plausible inputs the two anchors diverge (§6).

---

## 5. What the model can and cannot tell you

The model is deliberately explicit about *identifiability* — which quantities the data can actually pin down. It has more free parameters than independent anchors: four formal shares constrained by two anchors. As a consequence, the model identifies certain *combinations* of parameters sharply while leaving the individual values underdetermined. This is a property of the data, not a flaw in the method, and the model reports it rather than obscuring it.

Two structural features matter in particular. First, the stock scale and the effective lifetime enter the retirement calculation as a near-ratio: a range of (stock, lifetime) pairs produces nearly identical flows, so the data constrain their *ratio* well but the individual levels weakly. An external estimate of either quantity — most tractably, lifetime from fleet composition — transfers precision to the other. Second, the four formal shares trade off against one another along the chain and are best reported as a feasible *family* consistent with the anchors and the ordering constraint, not as four independent point values.

> **OPEN — Practical consequence.** The model's reliable outputs are structural and comparative — the scale of informal processing, the existence and size of an unrecorded refined-lead surplus, and the consistency or tension between reported stock and reported refining — rather than precise individual parameter values. Where a quantity is not separately identified, the model reports the constrained combination and the feasible range, not a single number.

---

## 6. Known limitations and open items

This is a proof-of-concept model, and its limitations define the work it is intended to launch.

**The stock series is not yet field-validated.** It is constructed bottom-up from vehicle-fleet data and carries known upward biases: registered-versus-active fleet counts (registrations include vehicles no longer on the road), a stock-versus-flow approximation in the segment gross-up, and an unpinned motorcycle-battery lead mass that has high leverage given the size of the two-wheeler fleet. A more accurate installed-lead estimate is the single highest-value input the proposed work would produce.

> **OPEN — Anchor reconciliation.** The installation and refining anchors are sensitive to the stock series and to β and τ. At the current defaults they sit within roughly 8% of joint balance, but that proximity depends on rough inputs; under alternative plausible values the two anchors diverge, implying that at least one reported input — installed stock, the battery share, or reported secondary production — requires correction. Quantifying and reconciling this tension with field data is a central objective of the proposed work, and the model's structure is designed to localize where the correction must fall.

**Informal manufacturing efficiency is the least certain efficiency assumption.** It is currently set close to the formal value; if informal assembly is materially less efficient, manufacturing output falls and the installation gap widens. By contrast, informal *refining* efficiency does not affect the USGS-anchored solve — the formal refined output is independent of it — which the model surfaces explicitly. This is a useful finding in itself: informal refining efficiency is not a lever for the refining anchor and need not be a field-research priority.

**Formality is modelled stage-by-stage.** Field evidence suggests the boundary may instead be operator-structured: operators tend to be formal or informal across all stages, with some selling of informal output into formal channels. The implied-crossover mechanism approximates this, but a more faithful operator-level structure is a candidate refinement once field data on operator behaviour are available.

> **OPEN — Trade attachment.** The precise point at which formal-only trade enters each stage (before or after the domestic formal/informal split) is a modelling convention rather than an observed quantity. The current treatment adds net trade to the formal lane after the split; field data on the formality of importers and exporters would let this be set empirically.

---

## 7. Files and reproducibility

The model is implemented in Python. The parallel chain is in `india_model/model_v5_parallel.py`, which exposes the forward chain, the informed default parameters, and the ordering and crossover checks. Segment lifetimes are in `india_model/segment_lifetimes.csv`; the consolidated input data — USGS production, BACI trade, and the installed-stock series for 2018–2023 — is in `india_model/india_mass_balance_2018_2023.csv`.

An interactive Streamlit dashboard runs on the parallel chain and provides:

- **Tab 1.** Stage-by-stage flow diagram with per-year volumes; node detail (formula / variables / assumptions); a line graph of major process flows; per-step flow table with CSV export.
- **Tab 2.** User-editable inputs: stock, segments, k, τ override, four formal shares (φ).
- **Tab 3.** This document.
- **Tab 4.** Diagnostics: calculation walkthrough, two residuals + three indicators, k/τ ridge, four φ↔η_I closed-form curves, feasibility map over (k, τ), parametric Monte Carlo.

Process-physics parameters (β, γ, and the eight η's) live in the **sidebar**. The dashboard is the authoritative current implementation of the model.

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

*End of overview — draft for technical review*
