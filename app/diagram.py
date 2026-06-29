"""Tab 1 — system flow diagram (matches India_Parallel_Formal_Informal_Diagram.pdf).

Topology:
    Collection ─→ BREAK_F ─→ SMELT_F ─→ REFINE_F ─→ MFG_F ─→ Installation
              ─→ BREAK_I ─→ SMELT_I ─→ REFINE_I ─→ MFG_I ──↗
    (formal top row, informal bottom row)

Trade attaches to the FORMAL lane only — used (854810) at BREAK, scrap (780200)
at SMELT, crude (780199) at REFINE, FEED + batteries at MFG. Primary USGS lead
and the "(1-β) non-battery" off-take sit at the refined-pool level (between
REFINE and MFG). USGS-secondary is a one-sided floor on REFINE_SEC_F. The
Installation node feeds back into Stock (closed loop).

The diagram is rendered as an embedded **React Flow** view loaded from esm.sh
inside an `st.components.v1.html` iframe — no PyPI dependency, drag/zoom/hover
work natively. Node detail (formula, variables, assumptions) is driven from
the selectbox in the right column (the iframe is one-way — click events can't
round-trip back to Python without a custom Streamlit component).

A static Plotly diagram with the same topology remains available as a fallback
(see `_plotly_diagram`).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from app.state import compute_state


# ============================================================================
# Node + edge catalogue (matches the PDF)
# ============================================================================
#
# Grid: x = column index (0..6), y = row index (top = -1 anchors / trade,
# 0 = formal lane, 1 = informal lane). Trade nodes float ABOVE the formal lane
# at their attachment column.

FORMAL_ROW   = 0.0
INFORMAL_ROW = 1.6
TRADE_ROW    = -1.2
ANCHOR_ROW   = -2.2

COL_COLLECT = 0
COL_BREAK   = 1
COL_SMELT   = 2
COL_REFINE  = 3
COL_MFG     = 4
COL_INSTALL = 5
COL_STOCK   = 6

# ---- formal/informal lane nodes (the chain proper) -------------------------

CHAIN_NODES = [
    # Collection
    {
        "id": "collect", "label": "Collection\n(Retired Batteries)",
        "pos": (COL_COLLECT, (FORMAL_ROW + INFORMAL_ROW) / 2),
        "chain_key": "COLLECT", "kind": "collect",
        "description":
            "Retired batteries are gathered into a single domestic pool. "
            "The formula multiplies retirement by γ because only some "
            "retired batteries actually reach a collector — informal "
            "scavenging, in-yard hoarding, and unrecorded resale divert "
            "the rest. The formal/informal split doesn't happen here yet; "
            "it happens at breaking.",
        "formula": r"\mathrm{COLLECT} = \gamma \cdot \mathrm{RETIRE}",
        "variables_keys": ["gamma"],
        "assumptions": "Single shared pool. RETIRE comes from the stock-"
                       "derived retirement engine (g, τ).",
    },
    # Formal lane
    {
        "id": "break_F", "label": "Breaking (Formal)", "lane": "F",
        "pos": (COL_BREAK, FORMAL_ROW),
        "chain_key": "out_break_F", "kind": "formal",
        "description":
            "Regulated dismantling at licensed facilities with proper "
            "acid containment and worker protection. The formula takes a "
            "share φ_break_f of collected batteries PLUS all imported "
            "used batteries (which clear formal customs), then multiplies "
            "by δ (Pb remaining at end-of-life) and η_break_F (the formal "
            "lane's recovery efficiency).",
        "formula": (r"\mathrm{in\_break}_F = \mathrm{COLLECT}\cdot\phi_{\mathrm{break}}^f"
                    r" + \Delta_{\mathrm{used}}"
                    r"\\ \mathrm{out\_break}_F = \mathrm{in\_break}_F \cdot \delta \cdot \eta_{\mathrm{break}}^F"),
        "variables_keys": ["phi_break_f", "delta", "eta_break_F"],
        "assumptions": "Used-battery trade (HS 854810) attaches to the formal "
                       "break input only — USAID notes external trade is "
                       "virtually all formal.",
    },
    {
        "id": "smelt_F", "label": "Smelting (Formal)", "lane": "F",
        "pos": (COL_SMELT, FORMAL_ROW),
        "chain_key": "out_smelt_F", "kind": "formal",
        "description":
            "Regulated smelting reduces lead scrap to crude lead at "
            "licensed smelters. The formula draws φ_smelt_f of the "
            "combined (formal + informal) scrap pool, plus all imported "
            "scrap. Because φ_smelt_f > φ_break_f by the USAID ordering, "
            "the formal smelt lane pulls in more scrap than formal "
            "breaking produces — the excess is informal-broken scrap "
            "sold up into formal smelters (the implied crossover).",
        "formula": (r"\mathrm{scrap\_total} = \mathrm{out\_break}_F + \mathrm{out\_break}_I"
                    r" + \Delta_{\mathrm{scrap}}"
                    r"\\ \mathrm{out\_smelt}_F = (\mathrm{scrap\_total}\cdot\phi_{\mathrm{smelt}}^f)"
                    r"\cdot\eta_{\mathrm{smelt}}^F"),
        "variables_keys": ["phi_smelt_f", "eta_smelt_F"],
        "assumptions": "Implied informal → formal crossover at this boundary: "
                       "in_smelt_F − out_break_F (see Diagnostics §4).",
    },
    {
        "id": "refine_F", "label": "Refining (Formal)", "lane": "F",
        "pos": (COL_REFINE, FORMAL_ROW),
        "chain_key": "REFINE_SEC_F", "kind": "formal",
        "description":
            "Regulated refining of crude lead to ≥99% purity. The "
            "formula draws φ_refine_f of the combined crude pool, plus "
            "all imported unrefined lead (HS 780199), and applies "
            "η_refine_F. This is the quantity USGS anchors against as a "
            "one-sided floor: the chain should meet or exceed the USGS "
            "secondary-refining figure.",
        "formula": (r"\mathrm{crude\_total} = \mathrm{out\_smelt}_F + \mathrm{out\_smelt}_I"
                    r" + \Delta_{\mathrm{crude}}"
                    r"\\ \mathrm{REFINE\_SEC}_F = (\mathrm{crude\_total}\cdot\phi_{\mathrm{refine}}^f)"
                    r"\cdot\eta_{\mathrm{refine}}^F"),
        "variables_keys": ["phi_refine_f", "eta_refine_F"],
        "assumptions": "USGS secondary refining anchors this quantity as a "
                       "one-sided floor. Overshoot is expected and represents "
                       "implied unrecorded refining.",
    },
    {
        "id": "mfg_F", "label": "Manufacturing (Formal)", "lane": "F",
        "pos": (COL_MFG, FORMAL_ROW),
        "chain_key": "MFG_F", "kind": "formal",
        "description":
            "Regulated battery assembly. The formula draws φ_mfg_f of "
            "the refined pool, multiplies by β (the share of refined "
            "lead that goes to batteries — the rest goes to paints, "
            "alloys, ammunition), and applies η_mfg_F. Battery parts "
            "(HS 850790) are battery-committed and bypass β: they're "
            "already destined for batteries, so the share discount "
            "doesn't apply.",
        "formula": (r"\mathrm{refined\_total} = \mathrm{REFINE\_SEC}_F + \mathrm{REFINE\_SEC}_I"
                    r" + \mathrm{PRIMARY}_{\mathrm{mined}} + \Delta_{\mathrm{feed}}"
                    r"\\ \mathrm{MFG}_F = (\mathrm{refined\_total}\cdot\phi_{\mathrm{mfg}}^f)"
                    r"\cdot\beta\cdot\eta_{\mathrm{mfg}}^F + \mathrm{parts}^+\cdot\eta_{\mathrm{mfg}}^F"),
        "variables_keys": ["phi_mfg_f", "beta", "eta_mfg_F"],
        "assumptions": "Battery parts (HS 850790) bypass β. Oxides "
                       "(HS 282410/282490) stay in FEED and remain subject to β.",
    },
    # Informal lane
    {
        "id": "break_I", "label": "Breaking (Informal)", "lane": "I",
        "pos": (COL_BREAK, INFORMAL_ROW),
        "chain_key": "out_break_I", "kind": "informal",
        "description":
            "Unregulated battery dismantling — typically backyard "
            "operations with no acid containment and direct worker "
            "exposure. The formula takes the (1 − φ_break_f) remainder "
            "of the collected pool and applies the lower informal "
            "recovery η_break_I. Trade does not enter here because "
            "external imports flow through formal customs.",
        "formula": (r"\mathrm{in\_break}_I = \mathrm{COLLECT}\cdot(1-\phi_{\mathrm{break}}^f)"
                    r"\\ \mathrm{out\_break}_I = \mathrm{in\_break}_I \cdot \delta \cdot \eta_{\mathrm{break}}^I"),
        "variables_keys": ["phi_break_f", "delta", "eta_break_I"],
        "assumptions": "Informal lane is purely domestic — no trade flows.",
    },
    {
        "id": "smelt_I", "label": "Smelting (Informal)", "lane": "I",
        "pos": (COL_SMELT, INFORMAL_ROW),
        "chain_key": "out_smelt_I", "kind": "informal",
        "description":
            "Unregulated smelting — typically in unsafe facilities with "
            "no flue-gas scrubbing. The formula takes (1 − φ_smelt_f) "
            "of the combined scrap pool and applies the much lower "
            "informal η_smelt_I (0.60 vs 0.97 formal). Output joins the "
            "shared crude pool.",
        "formula": r"\mathrm{out\_smelt}_I = (\mathrm{scrap\_total}\cdot(1-\phi_{\mathrm{smelt}}^f))\cdot\eta_{\mathrm{smelt}}^I",
        "variables_keys": ["phi_smelt_f", "eta_smelt_I"],
        "assumptions": "No trade flows.",
    },
    {
        "id": "refine_I", "label": "Refining (Informal)", "lane": "I",
        "pos": (COL_REFINE, INFORMAL_ROW),
        "chain_key": "REFINE_SEC_I", "kind": "informal",
        "description":
            "Unregulated refining — typically smelters that also refine "
            "without proper distillation columns. The formula takes "
            "(1 − φ_refine_f) of the combined crude pool. Because USGS "
            "does not see this output, any overshoot above USGS in the "
            "formal lane is the implied informal-but-formal-equivalent "
            "refined lead — this lane is its natural origin.",
        "formula": r"\mathrm{REFINE\_SEC}_I = (\mathrm{crude\_total}\cdot(1-\phi_{\mathrm{refine}}^f))\cdot\eta_{\mathrm{refine}}^I",
        "variables_keys": ["phi_refine_f", "eta_refine_I"],
        "assumptions": "Informal refined Pb is NOT counted by USGS.",
    },
    {
        "id": "mfg_I", "label": "Manufacturing (Informal)", "lane": "I",
        "pos": (COL_MFG, INFORMAL_ROW),
        "chain_key": "MFG_I", "kind": "informal",
        "description":
            "Unregulated battery assembly — typically small-scale "
            "operations. The formula takes (1 − φ_mfg_f) of the refined "
            "pool, β, and η_mfg_I. No parts bypass for the informal "
            "lane; β applies fully.",
        "formula": r"\mathrm{MFG}_I = (\mathrm{refined\_total}\cdot(1-\phi_{\mathrm{mfg}}^f))\cdot\beta\cdot\eta_{\mathrm{mfg}}^I",
        "variables_keys": ["phi_mfg_f", "beta", "eta_mfg_I"],
        "assumptions": "No parts bypass; β applies fully.",
    },
    # Installation (lanes rejoin)
    {
        "id": "install_implied", "label": "Installation\n(Batteries Entering Service)",
        "pos": (COL_INSTALL, (FORMAL_ROW + INFORMAL_ROW) / 2),
        "chain_key": "INSTALL_implied", "kind": "install",
        "description":
            "Both lanes' manufactured batteries plus net finished-"
            "battery imports become the installed stock. INSTALL_implied "
            "is the chain's SUPPLY of new batteries entering service; "
            "INSTALL_target (ΔStock + RETIRE) is the DEMAND derived from "
            "the reported stock series — the two-sided install anchor "
            "compares them.",
        "formula": (r"\mathrm{INSTALL\_implied} = \mathrm{MFG}_F + \mathrm{MFG}_I"
                    r" + \Delta_{\mathrm{batt}}"
                    r"\\ \mathrm{INSTALL\_target} = \Delta\mathrm{Stock} + \mathrm{RETIRE}"),
        "variables_keys": [],
        "assumptions": "Formal and informal batteries are both installed "
                       "(the lanes rejoin here).",
    },
]

# ---- trade nodes (formal-only inflows above the formal lane) ---------------

TRADE_NODES = [
    {
        "id": "used_trade", "label": "Trade — Used Batteries\n(HS 854810)",
        "pos": (COL_BREAK, TRADE_ROW),
        "chain_key": None, "kind": "trade",
        "description":
            "Net imports of used (end-of-life) batteries. USAID treats "
            "external trade as virtually all formal, so this attaches to "
            "the formal breaking input — imported used batteries arrive "
            "through legal customs and feed licensed breakers.",
        "formula": r"\Delta_{\mathrm{used}} = \mathrm{imp}_{854810} - \mathrm{exp}_{854810}",
        "variables_keys": [],
        "assumptions": "Formal-only by USAID convention.",
        "_attach": "break_F",
        "_chain_pair": ("imp_used", "exp_used"),
    },
    {
        "id": "scrap_trade", "label": "Trade — Lead Scrap\n(HS 780200)",
        "pos": (COL_SMELT, TRADE_ROW),
        "chain_key": None, "kind": "trade",
        "description":
            "Net imports of broken lead scrap (metallic Pb pieces from "
            "battery breaking). Attaches to the formal scrap pool only — "
            "the informal lane has no trade.",
        "formula": r"\Delta_{\mathrm{scrap}} = \mathrm{imp}_{780200} - \mathrm{exp}_{780200}",
        "variables_keys": [],
        "assumptions": "Formal-only.",
        "_attach": "smelt_F",
        "_chain_pair": ("imp_scrap", "exp_scrap"),
    },
    {
        "id": "crude_trade", "label": "Trade — Unrefined Lead\n(HS 780199)",
        "pos": (COL_REFINE, TRADE_ROW),
        "chain_key": None, "kind": "trade",
        "description":
            "Net imports of lead 'unrefined, other' (HS 780199) — crude "
            "lead from smelting that hasn't yet been refined to ≥99% "
            "purity. Attaches at the formal refining input.",
        "formula": r"\Delta_{\mathrm{crude}} = \mathrm{imp}_{780199} - \mathrm{exp}_{780199}",
        "variables_keys": [],
        "assumptions": "Formal-only; attaches between smelt and refine.",
        "_attach": "refine_F",
        "_chain_pair": ("imp_crude", "exp_crude"),
    },
    {
        "id": "feed_trade", "label": "Trade — Refined Feed\n+ Finished Batteries",
        "pos": (COL_MFG, TRADE_ROW),
        "chain_key": None, "kind": "trade",
        "description":
            "Two flows bundled together. **Refined feed** (HS 780110, "
            "780191, 282410, 282490) is refined-equivalent lead — pure "
            "lead, antimonial lead, and lead oxides — that joins the "
            "refined pool. **Finished batteries** (HS 850710 + 850720) "
            "skip manufacturing entirely and add directly to the "
            "installed stock.",
        "formula": (r"\Delta_{\mathrm{feed}} = \sum\mathrm{imp}_{\mathrm{FEED\,HS}} - \sum\mathrm{exp}_{\mathrm{FEED\,HS}}"
                    r"\\ \Delta_{\mathrm{batt}} = \mathrm{imp}_{8507\mathrm{x}0} - \mathrm{exp}_{8507\mathrm{x}0}"),
        "variables_keys": [],
        "assumptions": "Both formal-only.",
        "_attach": "mfg_F",
        "_chain_pair": None,
    },
    {
        "id": "primary_usgs", "label": "Mined Primary Lead\n(from ore, not recycled)",
        "pos": (COL_REFINE + 0.5, TRADE_ROW + 0.3),
        "chain_key": "REFINE_PRIMARY", "kind": "trade",
        "description":
            "Freshly mined lead — pulled out of the ground from "
            "domestic ore bodies (USGS-reported primary refined "
            "production). This is **never been in a battery before**; "
            "it's new lead entering the chain from mining, not recycled "
            "lead. The formula is just the USGS primary figure; it's "
            "exogenous to the chain.",
        "formula": r"\mathrm{PRIMARY}_{\mathrm{mined}} = \mathrm{USGS\,primary\,refined}",
        "variables_keys": [],
        "assumptions": "Treated as formal. Joins the refined pool before "
                       "manufacturing.",
        "_attach": "mfg_F",
    },
]

# ---- anchors (not flows, just references) ----------------------------------
# The USGS-anchor node was removed from the diagram per user request — the
# USGS-as-floor relationship is described in the refine_F node's description
# and tested numerically in Diagnostics §4.

ANCHOR_NODES = [
    {
        "id": "nonbatt", "label": "Non-Battery Uses\n((1 − β) of refined feed)",
        "pos": (COL_MFG - 0.5, ANCHOR_ROW),
        "chain_key": None, "kind": "anchor",
        "description":
            "The (1 − β) share of refined feed that goes to non-battery "
            "uses — paints, alloys, ammunition, cable sheathing. β is "
            "applied INSIDE the manufacturing formal/informal lanes, so "
            "the (1 − β) is what doesn't make it into batteries. Not "
            "tracked further in this model.",
        "formula": r"\mathrm{NB} = \mathrm{refined\_total}\cdot(1-\beta)\,\cdot\,(\text{never tracked further})",
        "variables_keys": ["beta"],
        "assumptions": "Information-only sink in the diagram.",
    },
    {
        "id": "stock", "label": "Lead in Service\n(Installed Stock)",
        "pos": (COL_STOCK, ANCHOR_ROW + 0.8),
        "chain_key": None, "kind": "anchor",
        "description":
            "The pool of lead currently installed in batteries in "
            "service. This is the closed-loop anchor: the chain installs "
            "new batteries into this stock, the stock ages, and a share "
            "retires each year and re-enters the chain through "
            "collection. INSTALL_target is the install demand the stock "
            "series implies.",
        "formula": (r"\mathrm{stock}_{\mathrm{eff}}(t) = k \cdot \mathrm{stock}(t)"
                    r"\\ \mathrm{INSTALL\_target} = \Delta\mathrm{Stock} + \mathrm{RETIRE}"),
        "variables_keys": ["k", "tau"],
        "assumptions": "Stock series constructed bottom-up from vehicle-fleet "
                       "data; field validation is the highest-priority refinement "
                       "(see README §6).",
    },
]

NODES = CHAIN_NODES + TRADE_NODES + ANCHOR_NODES


# ---- edges ----------------------------------------------------------------
# (source, target, kind)   kind ∈ {domestic, crossover, trade, anchor, closed_loop}

EDGES = [
    # Collection → break split
    ("collect", "break_F", "domestic"),
    ("collect", "break_I", "domestic"),

    # Formal lane down the chain
    ("break_F", "smelt_F", "domestic"),
    ("smelt_F", "refine_F", "domestic"),
    ("refine_F", "mfg_F",  "domestic"),
    ("mfg_F", "install_implied", "domestic"),

    # Informal lane down the chain
    ("break_I", "smelt_I", "domestic"),
    ("smelt_I", "refine_I", "domestic"),
    ("refine_I", "mfg_I",  "domestic"),
    ("mfg_I", "install_implied", "domestic"),

    # Implied informal → formal crossovers (purple dotted)
    ("break_I", "smelt_F",  "crossover"),
    ("smelt_I", "refine_F", "crossover"),
    ("refine_I", "mfg_F",   "crossover"),

    # Trade (green) — formal-lane only
    ("used_trade",   "break_F",  "trade"),
    ("scrap_trade",  "smelt_F",  "trade"),
    ("crude_trade",  "refine_F", "trade"),
    ("feed_trade",   "mfg_F",    "trade"),
    ("primary_usgs", "mfg_F",    "trade"),

    # Anchors (grey dotted)
    ("nonbatt", "mfg_F", "anchor"),

    # Closed loop
    ("install_implied", "stock", "closed_loop"),
    ("stock",           "collect", "closed_loop"),
]


# ============================================================================
# Helpers — per-node values
# ============================================================================

def _node_volume_at_year(node: dict, chain: dict, arr: dict, year: int) -> float | None:
    """Per-year volume in t Pb at `year`, or None if N/A."""
    idx = int(np.where(arr["year"] == year)[0][0])
    if node["chain_key"] is not None:
        return float(chain[node["chain_key"]][idx])
    pair = node.get("_chain_pair")
    if pair is not None:
        return float(arr[pair[0]][idx] - arr[pair[1]][idx])
    if node["id"] == "feed_trade":
        return float(
            (arr["imp_feed"][idx] - arr["exp_feed"][idx])
            + (arr["imp_batt"][idx] - arr["exp_batt"][idx])
        )
    return None


def _fmt_kt(x: float | None) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x / 1000:,.1f} kt"


def _format_variable(state: dict, key: str) -> str:
    """Render a single variable's current value from the canonical state."""
    if key in state["etas"]:
        return f"{state['etas'][key]:.2f}"
    if key in state["phi"]:
        return f"{state['phi'][key]:.2f}"
    if key == "beta":  return f"{state['beta']:.2f}"
    if key == "gamma": return f"{state['gamma']:.2f}"
    if key == "k":     return f"{state['k']:.2f}"
    if key == "tau":   return f"{state['tau_main']:.2f} yr"
    return "?"


# ============================================================================
# Plotly fallback diagram (faithful to the PDF)
# ============================================================================

def _kind_style(kind: str) -> dict:
    return {
        "collect":  {"fill": "#FBC02D", "text": "white"},
        "formal":   {"fill": "#1f77b4", "text": "white"},
        "informal": {"fill": "#ff7f0e", "text": "white"},
        "install":  {"fill": "#2ca02c", "text": "white"},
        "trade":    {"fill": "#FFF",    "text": "#1b5e20"},
        "anchor":   {"fill": "#E0E0E0", "text": "#333"},
    }.get(kind, {"fill": "#888", "text": "white"})


def _plotly_diagram(state: dict, year: int) -> go.Figure:
    chain = state["chain"]; arr = state["arr"]; etas = state["etas"]
    fig = go.Figure()

    # --- arrows first so nodes sit on top -----------------------------------
    pos_by_id = {n["id"]: n["pos"] for n in NODES}
    edge_styles = {
        "domestic":    dict(color="#333",  dash="solid"),
        "crossover":   dict(color="#9c27b0", dash="dot"),
        "trade":       dict(color="#2e7d32", dash="solid"),
        "anchor":      dict(color="#555",  dash="dot"),
        "closed_loop": dict(color="#666",  dash="solid"),
    }
    for src, tgt, kind in EDGES:
        if src not in pos_by_id or tgt not in pos_by_id:
            continue
        x0, y0 = pos_by_id[src]; x1, y1 = pos_by_id[tgt]
        style = edge_styles.get(kind, edge_styles["domestic"])
        fig.add_annotation(
            x=x1, y=y1, ax=x0, ay=y0,
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowsize=0.9, arrowwidth=1.3,
            arrowcolor=style["color"], standoff=22, startstandoff=22,
            opacity=0.85 if kind == "domestic" else 0.6,
        )

    # --- nodes --------------------------------------------------------------
    for n in NODES:
        x, y = n["pos"]
        kind = n["kind"]
        style = _kind_style(kind)
        vol = _node_volume_at_year(n, chain, arr, year)
        # Label = name + volume. η values are intentionally NOT shown on the
        # diagram — they live in the sidebar and in each node's detail panel.
        body = n["label"]
        if vol is not None:
            body = f"{body}<br><b>{_fmt_kt(vol)}</b>"
        # ellipse for collect/install/anchors, rectangle for chain stages
        if kind in ("collect", "install", "anchor"):
            fig.add_shape(type="circle",
                          x0=x - 0.42, x1=x + 0.42, y0=y - 0.35, y1=y + 0.35,
                          fillcolor=style["fill"],
                          line=dict(color="#222", width=1),
                          opacity=1.0 if kind != "anchor" else 0.7,
                          layer="above")
        else:
            border = "#1565c0" if kind == "formal" else ("#e65100" if kind == "informal" else "#2e7d32")
            fig.add_shape(type="rect",
                          x0=x - 0.42, x1=x + 0.42, y0=y - 0.35, y1=y + 0.35,
                          fillcolor=style["fill"], line=dict(color=border, width=1.2),
                          opacity=1.0, layer="above")
        fig.add_annotation(
            x=x, y=y, text=body, showarrow=False,
            font=dict(color=style["text"], size=10),
            align="center", xanchor="center", yanchor="middle",
        )

    # --- Lane labels (FORMAL / INFORMAL) -----------------------------------
    fig.add_annotation(x=COL_COLLECT - 1.0, y=FORMAL_ROW,   text="<b>FORMAL</b>",
                       showarrow=False, font=dict(color="#1565c0", size=12),
                       xanchor="left")
    fig.add_annotation(x=COL_COLLECT - 1.0, y=INFORMAL_ROW, text="<b>INFORMAL</b>",
                       showarrow=False, font=dict(color="#e65100", size=12),
                       xanchor="left")

    # --- layout -------------------------------------------------------------
    fig.update_layout(
        height=560, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(visible=False, range=[-1.5, COL_STOCK + 1.0]),
        yaxis=dict(visible=False, range=[INFORMAL_ROW + 0.8,
                                         ANCHOR_ROW - 0.4],
                   autorange=False, scaleanchor=None),
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


# ============================================================================
# React Flow embed via CDN (st.components.v1.html iframe)
# ============================================================================

# Lane η lookup keys
ETA_LOOKUP = {
    "break_F": "eta_break_F", "smelt_F": "eta_smelt_F",
    "refine_F": "eta_refine_F", "mfg_F": "eta_mfg_F",
    "break_I": "eta_break_I", "smelt_I": "eta_smelt_I",
    "refine_I": "eta_refine_I", "mfg_I": "eta_mfg_I",
}

# Per-node colour styling for the React Flow render
NODE_COLOURS = {
    "collect":  ("#FBC02D", "#000"),
    "formal":   ("#1f77b4", "#fff"),
    "informal": ("#ff7f0e", "#fff"),
    "install":  ("#2ca02c", "#fff"),
    "trade":    ("#E8F5E9", "#1b5e20"),
    "anchor":   ("#E0E0E0", "#333"),
}

EDGE_COLOURS = {
    "domestic":    "#333",
    "crossover":   "#9c27b0",
    "trade":       "#2e7d32",
    "anchor":      "#666",
    "closed_loop": "#666",
}


def _build_react_flow_payload(state: dict, year: int) -> tuple[list, list]:
    """Return (nodes, edges) in React Flow's JSON shape."""
    chain = state["chain"]; arr = state["arr"]; etas = state["etas"]

    rf_nodes = []
    for n in NODES:
        x, y = n["pos"]
        vol = _node_volume_at_year(n, chain, arr, year)
        bg, fg = NODE_COLOURS.get(n["kind"], ("#888", "#fff"))
        # η values are intentionally NOT shown on the diagram — they live
        # in the sidebar and in each node's detail panel.
        vol_line = f"\n{_fmt_kt(vol)}" if vol is not None else ""
        label_text = f"{n['label']}{vol_line}"
        # Border colour signals the lane
        border = {
            "formal":   "#1565c0",
            "informal": "#e65100",
            "collect":  "#f9a825",
            "install":  "#1b5e20",
            "trade":    "#2e7d32",
            "anchor":   "#666",
        }.get(n["kind"], "#222")
        # Node shape — circles for anchors / collect / install, rounded boxes for stages
        border_radius = "50%" if n["kind"] in ("collect", "install", "anchor") else "10px"
        rf_nodes.append({
            "id":   n["id"],
            "type": "default",
            "position": {"x": int(x * 200), "y": int(y * 130) + 220},  # +220 to give top trade row room
            "data": {"label": label_text},
            "style": {
                "background": bg,
                "color":      fg,
                "border":     f"2px solid {border}",
                "borderRadius": border_radius,
                "width":      160,
                "height":     "auto",
                "fontSize":   "11px",
                "padding":    "8px",
                "whiteSpace": "pre-wrap",
                "textAlign":  "center",
                "lineHeight": "1.25",
            },
            "draggable": True,
        })

    rf_edges = []
    for src, tgt, kind in EDGES:
        stroke = EDGE_COLOURS.get(kind, "#333")
        dasharray = "6 4" if kind in ("crossover", "anchor") else None
        rf_edges.append({
            "id":      f"{src}-{tgt}",
            "source":  src,
            "target":  tgt,
            "type":    "smoothstep",
            "animated": (kind == "domestic"),
            "style":   {"stroke": stroke,
                        **({"strokeDasharray": dasharray} if dasharray else {})},
            "markerEnd": {"type": "arrowclosed", "color": stroke},
        })
    return rf_nodes, rf_edges


def _react_flow_html(state: dict, year: int, height: int = 620) -> str:
    """Self-contained HTML page that loads React Flow from esm.sh and renders
    the diagram. Embed via `st.components.v1.html(html, height=...)`."""
    rf_nodes, rf_edges = _build_react_flow_payload(state, year)
    nodes_json = json.dumps(rf_nodes)
    edges_json = json.dumps(rf_edges)
    # Importmap-based ESM loader (esm.sh). React Flow CSS is loaded as a
    # stylesheet via the same CDN. Pinned to v11 (stable; v12 introduced
    # breaking API changes).
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>India parallel chain — React Flow</title>
  <link rel="stylesheet" href="https://esm.sh/reactflow@11.11.4/dist/style.css">
  <style>
    html, body {{ margin: 0; padding: 0; height: 100%;
                  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                               Roboto, sans-serif; }}
    #app   {{ width: 100%; height: {height}px; }}
    .react-flow__node {{ box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
    .lane-label {{
      position: absolute; left: 8px; padding: 4px 8px; font-weight: 600;
      font-size: 12px; border-radius: 4px; z-index: 10;
      background: rgba(255,255,255,0.85);
    }}
    .lane-label.formal   {{ top: 220px; color: #1565c0; }}
    .lane-label.informal {{ top: 350px; color: #e65100; }}
    .fallback {{ padding: 20px; color: #b71c1c; font-family: sans-serif; }}
  </style>
</head>
<body>
  <div id="app">
    <div class="fallback" id="fallback">
      Loading React Flow from esm.sh…<br>
      <small>If this message stays, the network is blocking esm.sh — the
      Plotly fallback diagram is below the iframe.</small>
    </div>
  </div>
  <div class="lane-label formal">FORMAL</div>
  <div class="lane-label informal">INFORMAL</div>
  <script type="importmap">
  {{
    "imports": {{
      "react":             "https://esm.sh/react@18.3.1",
      "react/jsx-runtime": "https://esm.sh/react@18.3.1/jsx-runtime",
      "react-dom":         "https://esm.sh/react-dom@18.3.1",
      "react-dom/client":  "https://esm.sh/react-dom@18.3.1/client",
      "reactflow":         "https://esm.sh/reactflow@11.11.4?deps=react@18.3.1,react-dom@18.3.1"
    }}
  }}
  </script>
  <script type="module">
    try {{
      const React    = (await import("react")).default;
      const ReactDOM = (await import("react-dom/client")).default;
      const RF       = await import("reactflow");
      const ReactFlow = RF.default;
      const {{ Background, Controls, MiniMap }} = RF;

      const nodes = {nodes_json};
      const edges = {edges_json};

      function App() {{
        return React.createElement(
          "div",
          {{ style: {{ width: "100%", height: "{height}px" }} }},
          React.createElement(
            ReactFlow,
            {{
              defaultNodes: nodes,
              defaultEdges: edges,
              fitView: true,
              fitViewOptions: {{ padding: 0.15 }},
              minZoom: 0.3,
              maxZoom: 2.5,
              proOptions: {{ hideAttribution: true }},
            }},
            React.createElement(Background, {{ gap: 18, color: "#eee" }}),
            React.createElement(Controls, {{ showInteractive: false }}),
            React.createElement(MiniMap, {{
              zoomable: true, pannable: true, nodeStrokeWidth: 2,
              style: {{ background: "#fafafa" }}
            }}),
          )
        );
      }}

      const root = ReactDOM.createRoot(document.getElementById("app"));
      root.render(React.createElement(App));
    }} catch (err) {{
      document.getElementById("fallback").innerHTML =
        "<b>React Flow failed to load.</b><br><small>"
        + String(err) + "</small><br>"
        + "<small>Reload the page; if the problem persists, "
        + "the deploy's network may be blocking esm.sh.</small>";
    }}
  </script>
</body>
</html>"""


# ============================================================================
# Legacy streamlit-flow library detection (kept for future, currently unused)
# ============================================================================

def _try_flow_lib():
    """Return ('mod_name', namespace_dict) for whichever flow library imports."""
    # 1. streamlit-flow (dkapur17's actively-maintained fork; pip: streamlit-flow-swc)
    try:
        from streamlit_flow import streamlit_flow  # type: ignore
        from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge  # type: ignore
        from streamlit_flow.state import StreamlitFlowState  # type: ignore
        return "streamlit_flow", dict(
            streamlit_flow=streamlit_flow,
            StreamlitFlowNode=StreamlitFlowNode,
            StreamlitFlowEdge=StreamlitFlowEdge,
            StreamlitFlowState=StreamlitFlowState,
        )
    except Exception:
        pass
    # 2. ChrisDelClea's older streamlit-flow-component
    try:
        from streamlit_flow_component import st_flow  # type: ignore
        return "streamlit_flow_component", dict(st_flow=st_flow)
    except Exception:
        pass
    return None, None


def _flow_diagram_streamlit_flow(state: dict, year: int, ns: dict):
    """Render with dkapur17's streamlit_flow library."""
    chain = state["chain"]; arr = state["arr"]; etas = state["etas"]
    SFN = ns["StreamlitFlowNode"]
    SFE = ns["StreamlitFlowEdge"]
    SFState = ns["StreamlitFlowState"]
    sf = ns["streamlit_flow"]

    nodes = []
    for n in NODES:
        x, y = n["pos"]
        vol = _node_volume_at_year(n, chain, arr, year)
        vol_str = _fmt_kt(vol) if vol is not None else ""
        style = _kind_style(n["kind"])
        label = n["label"].replace("\n", " — ")
        content = f"**{label}**\n\n{vol_str}"
        nodes.append(SFN(
            id=n["id"],
            pos=(x * 180, y * 110),
            data={"content": content},
            node_type="default",
            source_position="right",
            target_position="left",
            style={"backgroundColor": style["fill"], "color": style["text"],
                   "borderRadius": "8px", "padding": "6px", "width": 160,
                   "fontSize": "11px"},
            draggable=True,
        ))
    edges = []
    edge_colors = {
        "domestic":    "#333",
        "crossover":   "#9c27b0",
        "trade":       "#2e7d32",
        "anchor":      "#555",
        "closed_loop": "#666",
    }
    for src, tgt, kind in EDGES:
        edges.append(SFE(
            id=f"{src}-{tgt}",
            source=src, target=tgt,
            animated=(kind == "domestic"),
            marker_end={"type": "arrow"},
            style={"stroke": edge_colors.get(kind, "#333"),
                   "strokeDasharray": "4 4" if kind in ("crossover", "anchor") else None},
        ))

    flow_state = SFState(nodes=nodes, edges=edges)
    try:
        result = sf("india_flow", flow_state, fit_view=True, height=560,
                    get_node_on_click=True, show_minimap=False)
    except Exception:
        return None, False
    selected = None
    try:
        selected = getattr(result, "selected_id", None)
    except Exception:
        selected = None
    return selected, True


def _flow_diagram_chrisdelclea(state: dict, year: int, ns: dict):
    """Render with ChrisDelClea's older streamlit_flow_component library."""
    chain = state["chain"]; arr = state["arr"]
    st_flow = ns["st_flow"]
    nodes, edges = [], []
    for n in NODES:
        x, y = n["pos"]
        vol = _node_volume_at_year(n, chain, arr, year)
        vol_str = _fmt_kt(vol) if vol is not None else ""
        style = _kind_style(n["kind"])
        nodes.append({
            "id": n["id"], "type": "default",
            "data": {"label": f"{n['label'].replace(chr(10), ' / ')}\n{vol_str}"},
            "position": {"x": x * 180, "y": y * 110},
            "style": {"background": style["fill"], "color": style["text"],
                      "borderRadius": "8px", "padding": "8px", "width": 160},
        })
    for src, tgt, kind in EDGES:
        edges.append({
            "id": f"{src}-{tgt}", "source": src, "target": tgt,
            "animated": (kind == "domestic"),
            "type": "smoothstep",
        })
    try:
        result = st_flow(nodes=nodes, edges=edges, key="india_flow",
                         height=560, fit_view=True)
    except Exception:
        return None, False
    selected = None
    try:
        if isinstance(result, dict):
            selected = result.get("selected") or result.get("clicked_node")
    except Exception:
        pass
    return selected, True


# ============================================================================
# Side panel — node detail
# ============================================================================

def _render_node_detail(node: dict, state: dict) -> None:
    chain = state["chain"]; arr = state["arr"]
    st.markdown(f"### {node['label'].replace(chr(10), ' — ')}")
    st.caption(f"id: `{node['id']}` · kind: `{node['kind']}`")

    # Plain-English description: what this step is and why the formula has its
    # form. Rendered prominently as the first thing under the title.
    description = node.get("description")
    if description:
        st.markdown(f"**What this is.** {description}")

    st.markdown("**Formula**")
    st.latex(node["formula"])

    keys = node.get("variables_keys") or []
    if keys:
        st.markdown("**Variables (current values)**")
        var_df = pd.DataFrame(
            [(k, _format_variable(state, k)) for k in keys],
            columns=["symbol", "value"],
        )
        st.dataframe(var_df, hide_index=True, use_container_width=True)

    st.markdown("**Per-year volume (t Pb)**")
    years = arr["year"]
    vols = [_node_volume_at_year(node, chain, arr, int(y)) for y in years]
    val_df = pd.DataFrame({
        "Year":          [int(y) for y in years],
        "Volume (t Pb)": [None if v is None else round(v, 0) for v in vols],
    })
    st.dataframe(val_df, hide_index=True, use_container_width=True)

    st.markdown("**Assumptions / notes**")
    st.markdown(node["assumptions"])


# ============================================================================
# Line graph
# ============================================================================

def _render_line_graph(state: dict) -> None:
    chain = state["chain"]; arr = state["arr"]
    years = arr["year"]
    # Major chain flows only — anchors (USGS, INSTALL_target) intentionally omitted
    # so the curves don't crowd. The anchors are in §4 of the Diagnostics tab.
    series = [
        ("COLLECT",         chain["COLLECT"],          "#FBC02D"),
        ("BREAK_total",     chain["BREAK_total"],      "#9467bd"),
        ("SMELT_total",     chain["SMELT_total"],      "#8c564b"),
        ("REFINE_SEC_F",    chain["REFINE_SEC_F"],     "#d62728"),
        ("MFG_total",       chain["MFG_total"],        "#2ca02c"),
        ("INSTALL_implied", chain["INSTALL_implied"],  "#000000"),
    ]
    fig = go.Figure()
    for name, vec, color in series:
        fig.add_trace(go.Scatter(
            x=years, y=vec, mode="lines+markers", name=name,
            line=dict(color=color, width=2),
            hovertemplate=f"{name}<br>%{{x}}: %{{y:,.0f}} t Pb<extra></extra>",
        ))
    # Force x-axis to sit at the bottom of the plotting area (not at y=0 inside).
    fig.update_layout(
        height=420,
        margin=dict(l=50, r=20, t=50, b=120),
        title=dict(text="Major process steps — fit window", x=0, xanchor="left"),
        xaxis=dict(
            title=dict(text="Year", standoff=12),
            tickmode="array",
            tickvals=[int(y) for y in years],
            ticktext=[str(int(y)) for y in years],
            anchor="free", position=0,  # axis line at the bottom of the plot
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="t Pb / yr"),
            zeroline=False,
            rangemode="tozero",
        ),
        legend=dict(orientation="h", yanchor="top", y=-0.20, x=0.0),
    )
    st.plotly_chart(fig, use_container_width=True, theme="streamlit")


# ============================================================================
# Per-step flow table (collapsible, with CSV export)
# ============================================================================

# Columns for the export — covers every node in the diagram + the anchor pair.
FLOW_TABLE_COLUMNS = [
    ("RETIRE",            "RETIRE",           "chain"),
    ("COLLECT",           "COLLECT",          "chain"),
    ("imp_used (854810)", "imp_used",         "arr"),
    ("exp_used (854810)", "exp_used",         "arr"),
    ("in_break_F",        "in_break_F",       "chain"),
    ("in_break_I",        "in_break_I",       "chain"),
    ("out_break_F",       "out_break_F",      "chain"),
    ("out_break_I",       "out_break_I",      "chain"),
    ("BREAK_total",       "BREAK_total",      "chain"),
    ("imp_scrap (780200)","imp_scrap",        "arr"),
    ("exp_scrap (780200)","exp_scrap",        "arr"),
    ("scrap_total",       "scrap_total",      "chain"),
    ("in_smelt_F",        "in_smelt_F",       "chain"),
    ("in_smelt_I",        "in_smelt_I",       "chain"),
    ("out_smelt_F",       "out_smelt_F",      "chain"),
    ("out_smelt_I",       "out_smelt_I",      "chain"),
    ("SMELT_total",       "SMELT_total",      "chain"),
    ("imp_crude (780199)","imp_crude",        "arr"),
    ("exp_crude (780199)","exp_crude",        "arr"),
    ("crude_total",       "crude_total",      "chain"),
    ("in_refine_F",       "in_refine_F",      "chain"),
    ("in_refine_I",       "in_refine_I",      "chain"),
    ("REFINE_SEC_F",      "REFINE_SEC_F",     "chain"),
    ("REFINE_SEC_I",      "REFINE_SEC_I",     "chain"),
    ("REFINE_SEC_total",  "REFINE_SEC_total", "chain"),
    ("REFINE_PRIMARY (USGS)", "REFINE_PRIMARY","chain"),
    ("imp_feed",          "imp_feed",         "arr"),
    ("exp_feed",          "exp_feed",         "arr"),
    ("refined_total",     "refined_total",    "chain"),
    ("imp_parts (850790)","imp_parts",        "arr"),
    ("exp_parts (850790)","exp_parts",        "arr"),
    ("NET_PARTS",         "NET_PARTS",        "chain"),
    ("in_mfg_F",          "in_mfg_F",         "chain"),
    ("in_mfg_I",          "in_mfg_I",         "chain"),
    ("MFG_F",             "MFG_F",            "chain"),
    ("MFG_I",             "MFG_I",            "chain"),
    ("MFG_total",         "MFG_total",        "chain"),
    ("imp_batt (850710+850720)", "imp_batt",  "arr"),
    ("exp_batt (850710+850720)", "exp_batt",  "arr"),
    ("INSTALL_implied",   "INSTALL_implied",  "chain"),
    ("INSTALL_target",    "INSTALL_target",   "chain"),
    ("dStock",            "dStock",           "chain"),
    ("xover_smelt",       "xover_smelt",      "chain"),
    ("xover_refine",      "xover_refine",     "chain"),
    ("xover_mfg",         "xover_mfg",        "chain"),
    ("USGS secondary",    "sec_usgs",         "arr"),
    ("USGS primary",      "prim_usgs",        "arr"),
]


def _build_flow_dataframe(state: dict) -> pd.DataFrame:
    """Long-format DataFrame: rows = process steps, columns = years.

    Numbers in tonnes of contained Pb. Used for both display and CSV export.
    """
    chain = state["chain"]; arr = state["arr"]
    years = [int(y) for y in arr["year"]]
    rows = []
    for label, key, src in FLOW_TABLE_COLUMNS:
        vec = (chain.get(key) if src == "chain" else arr.get(key))
        if vec is None:
            continue
        row = {"Step": label}
        for i, y in enumerate(years):
            row[str(y)] = float(vec[i])
        rows.append(row)
    return pd.DataFrame(rows)


def _render_flow_table(state: dict) -> None:
    df = _build_flow_dataframe(state)
    years = [c for c in df.columns if c != "Step"]
    # Pretty-print with thousands separators for the on-screen view
    df_disp = df.copy()
    for y in years:
        df_disp[y] = df_disp[y].map(lambda v: f"{v:,.0f}")
    st.dataframe(df_disp, hide_index=True, use_container_width=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name="india_per_step_flows.csv",
        mime="text/csv",
        help="Per-step volumes for every year in the fit window, in tonnes of contained Pb.",
    )


# ============================================================================
# Tab entry point
# ============================================================================

def render() -> None:
    state = compute_state()
    arr = state["arr"]

    st.markdown("### System flow — parallel formal/informal chain")
    st.caption(
        f"Volumes in nodes are for the selected year. **k = {state['k']:.2f}, "
        f"τ = {state['tau_main']:.2f} yr, β = {state['beta']:.2f}, "
        f"γ = {state['gamma']:.2f}.** Edit any input in Tab 2 or the sidebar "
        "and the diagram updates."
    )

    years = arr["year"].astype(int).tolist()
    cols = st.columns([2, 6])
    with cols[0]:
        year = int(st.selectbox(
            "Year (for node volumes)", options=years,
            index=len(years) - 1, key="diagram_year",
        ))

    # ----- Flow diagram (full width) ---------------------------------------
    html = _react_flow_html(state, year, height=640)
    components.html(html, height=660, scrolling=False)

    # ----- Node detail (full width, BELOW the diagram) ---------------------
    st.divider()
    st.markdown("##### Node detail")
    node_choices = [n["id"] for n in NODES]
    chosen = st.selectbox(
        "Pick a node", options=node_choices,
        index=node_choices.index("install_implied"),
        key="diagram_node",
        format_func=lambda i: next(n["label"].replace("\n", " — ")
                                   for n in NODES if n["id"] == i),
    )
    node = next(n for n in NODES if n["id"] == chosen)
    _render_node_detail(node, state)

    # ----- Line graph ------------------------------------------------------
    st.divider()
    _render_line_graph(state)

    # ----- Per-step flow table (collapsible, with CSV export) --------------
    st.divider()
    with st.expander("Per-step flow table (all values, CSV export)",
                     expanded=False):
        st.caption(
            "Every per-step quantity for every year in the fit window, in tonnes "
            "of contained lead. Use the **Download CSV** button to export."
        )
        _render_flow_table(state)

    # ----- Static Plotly diagram (fallback / printable view) ---------------
    with st.expander("Static Plotly diagram (fallback / printable view)",
                     expanded=False):
        fig = _plotly_diagram(state, year)
        st.plotly_chart(fig, use_container_width=True, theme="streamlit",
                        config={"displayModeBar": False})
