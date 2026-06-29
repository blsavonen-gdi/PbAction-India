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

The diagram tries two streamlit React-Flow wrappers in order:
    1. streamlit_flow      (active fork — streamlit-flow-swc on PyPI)
    2. streamlit_flow_component (the older ChrisDelClea library)
If neither is installed or both fail, falls back to a styled Plotly diagram
with the same node positions and edge styling. Either way, a year selector
above the diagram changes the per-node volumes, and the right-hand panel
shows the selected node's equation + per-year values + assumptions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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
        "id": "collect", "label": "Collection\n(retired batt.)",
        "pos": (COL_COLLECT, (FORMAL_ROW + INFORMAL_ROW) / 2),
        "chain_key": "COLLECT", "kind": "collect",
        "formula": r"\mathrm{COLLECT} = \gamma \cdot \mathrm{RETIRE}",
        "variables_keys": ["gamma"],
        "assumptions": "Single shared pool. The formal/informal split happens at "
                       "BREAK, not here. RETIRE comes from the stock-derived "
                       "retirement engine (g, τ).",
    },
    # Formal lane
    {
        "id": "break_F", "label": "BREAK", "lane": "F",
        "pos": (COL_BREAK, FORMAL_ROW),
        "chain_key": "out_break_F", "kind": "formal",
        "formula": (r"\mathrm{in\_break}_F = \mathrm{COLLECT}\cdot\phi_{\mathrm{break}}^f"
                    r" + \Delta_{\mathrm{used}}"
                    r"\\ \mathrm{out\_break}_F = \mathrm{in\_break}_F \cdot \delta \cdot \eta_{\mathrm{break}}^F"),
        "variables_keys": ["phi_break_f", "delta", "eta_break_F"],
        "assumptions": "Used-battery trade (854810) attaches to the formal break "
                       "input only — USAID: external trade is virtually all formal.",
    },
    {
        "id": "smelt_F", "label": "SMELT", "lane": "F",
        "pos": (COL_SMELT, FORMAL_ROW),
        "chain_key": "out_smelt_F", "kind": "formal",
        "formula": (r"\mathrm{scrap\_total} = \mathrm{out\_break}_F + \mathrm{out\_break}_I"
                    r" + \Delta_{\mathrm{scrap}}"
                    r"\\ \mathrm{out\_smelt}_F = (\mathrm{scrap\_total}\cdot\phi_{\mathrm{smelt}}^f)"
                    r"\cdot\eta_{\mathrm{smelt}}^F"),
        "variables_keys": ["phi_smelt_f", "eta_smelt_F"],
        "assumptions": "Implied informal → formal crossover at this boundary: "
                       "in_smelt_F − out_break_F (see §4 crossover indicator).",
    },
    {
        "id": "refine_F", "label": "REFINE", "lane": "F",
        "pos": (COL_REFINE, FORMAL_ROW),
        "chain_key": "REFINE_SEC_F", "kind": "formal",
        "formula": (r"\mathrm{crude\_total} = \mathrm{out\_smelt}_F + \mathrm{out\_smelt}_I"
                    r" + \Delta_{\mathrm{crude}}"
                    r"\\ \mathrm{REFINE\_SEC}_F = (\mathrm{crude\_total}\cdot\phi_{\mathrm{refine}}^f)"
                    r"\cdot\eta_{\mathrm{refine}}^F"),
        "variables_keys": ["phi_refine_f", "eta_refine_F"],
        "assumptions": "**USGS secondary anchors REFINE_SEC_F as a one-sided floor.** "
                       "Overshoot is expected = implied unrecorded refining.",
    },
    {
        "id": "mfg_F", "label": "MFG", "lane": "F",
        "pos": (COL_MFG, FORMAL_ROW),
        "chain_key": "MFG_F", "kind": "formal",
        "formula": (r"\mathrm{refined\_total} = \mathrm{REFINE\_SEC}_F + \mathrm{REFINE\_SEC}_I"
                    r" + \mathrm{PRIMARY}_{\mathrm{USGS}} + \Delta_{\mathrm{feed}}"
                    r"\\ \mathrm{MFG}_F = (\mathrm{refined\_total}\cdot\phi_{\mathrm{mfg}}^f)"
                    r"\cdot\beta\cdot\eta_{\mathrm{mfg}}^F + \mathrm{parts}^+\cdot\eta_{\mathrm{mfg}}^F"),
        "variables_keys": ["phi_mfg_f", "beta", "eta_mfg_F"],
        "assumptions": "Battery parts (850790) bypass β; oxides (282410/282490) "
                       "stay in FEED and remain subject to β. (1-β) leaves to "
                       "non-battery uses.",
    },
    # Informal lane
    {
        "id": "break_I", "label": "BREAK", "lane": "I",
        "pos": (COL_BREAK, INFORMAL_ROW),
        "chain_key": "out_break_I", "kind": "informal",
        "formula": (r"\mathrm{in\_break}_I = \mathrm{COLLECT}\cdot(1-\phi_{\mathrm{break}}^f)"
                    r"\\ \mathrm{out\_break}_I = \mathrm{in\_break}_I \cdot \delta \cdot \eta_{\mathrm{break}}^I"),
        "variables_keys": ["phi_break_f", "delta", "eta_break_I"],
        "assumptions": "Informal lane is purely domestic — no trade flows in or out.",
    },
    {
        "id": "smelt_I", "label": "SMELT", "lane": "I",
        "pos": (COL_SMELT, INFORMAL_ROW),
        "chain_key": "out_smelt_I", "kind": "informal",
        "formula": r"\mathrm{out\_smelt}_I = (\mathrm{scrap\_total}\cdot(1-\phi_{\mathrm{smelt}}^f))\cdot\eta_{\mathrm{smelt}}^I",
        "variables_keys": ["phi_smelt_f", "eta_smelt_I"],
        "assumptions": "Output joins the shared crude pool.",
    },
    {
        "id": "refine_I", "label": "REFINE", "lane": "I",
        "pos": (COL_REFINE, INFORMAL_ROW),
        "chain_key": "REFINE_SEC_I", "kind": "informal",
        "formula": r"\mathrm{REFINE\_SEC}_I = (\mathrm{crude\_total}\cdot(1-\phi_{\mathrm{refine}}^f))\cdot\eta_{\mathrm{refine}}^I",
        "variables_keys": ["phi_refine_f", "eta_refine_I"],
        "assumptions": "Informal refined Pb is NOT counted by USGS — it could be "
                       "the explanation for any REFINE_SEC_F overshoot above USGS.",
    },
    {
        "id": "mfg_I", "label": "MFG", "lane": "I",
        "pos": (COL_MFG, INFORMAL_ROW),
        "chain_key": "MFG_I", "kind": "informal",
        "formula": r"\mathrm{MFG}_I = (\mathrm{refined\_total}\cdot(1-\phi_{\mathrm{mfg}}^f))\cdot\beta\cdot\eta_{\mathrm{mfg}}^I",
        "variables_keys": ["phi_mfg_f", "beta", "eta_mfg_I"],
        "assumptions": "No parts bypass for the informal lane; β applies fully.",
    },
    # Installation (lanes rejoin)
    {
        "id": "install_implied", "label": "Installation\n(in service)",
        "pos": (COL_INSTALL, (FORMAL_ROW + INFORMAL_ROW) / 2),
        "chain_key": "INSTALL_implied", "kind": "install",
        "formula": (r"\mathrm{INSTALL\_implied} = \mathrm{MFG}_F + \mathrm{MFG}_I"
                    r" + \Delta_{\mathrm{batt}}"
                    r"\\ \mathrm{INSTALL\_target} = \Delta\mathrm{Stock} + \mathrm{RETIRE}"),
        "variables_keys": [],
        "assumptions": "The lanes rejoin here — both formal and informal batteries "
                       "are installed. INSTALL_implied vs INSTALL_target is the "
                       "two-sided install anchor.",
    },
]

# ---- trade nodes (formal-only inflows above the formal lane) ---------------

TRADE_NODES = [
    {
        "id": "used_trade", "label": "imp/exp used batt.\n(854810)",
        "pos": (COL_BREAK, TRADE_ROW),
        "chain_key": None, "kind": "trade",
        "formula": r"\Delta_{\mathrm{used}} = \mathrm{imp}_{854810} - \mathrm{exp}_{854810}",
        "variables_keys": [],
        "assumptions": "Imported used batteries flow through legal customs into "
                       "formal breakers (USAID: external trade ≈ all formal).",
        "_attach": "break_F",
        "_chain_pair": ("imp_used", "exp_used"),
    },
    {
        "id": "scrap_trade", "label": "imp/exp scrap\n(780200)",
        "pos": (COL_SMELT, TRADE_ROW),
        "chain_key": None, "kind": "trade",
        "formula": r"\Delta_{\mathrm{scrap}} = \mathrm{imp}_{780200} - \mathrm{exp}_{780200}",
        "variables_keys": [],
        "assumptions": "Attaches to the formal scrap pool only.",
        "_attach": "smelt_F",
        "_chain_pair": ("imp_scrap", "exp_scrap"),
    },
    {
        "id": "crude_trade", "label": "imp/exp crude\n(780199)",
        "pos": (COL_REFINE, TRADE_ROW),
        "chain_key": None, "kind": "trade",
        "formula": r"\Delta_{\mathrm{crude}} = \mathrm{imp}_{780199} - \mathrm{exp}_{780199}",
        "variables_keys": [],
        "assumptions": "Lead, unrefined other — attaches between smelt and refine, formal-only.",
        "_attach": "refine_F",
        "_chain_pair": ("imp_crude", "exp_crude"),
    },
    {
        "id": "feed_trade", "label": "imp/exp FEED + batt\n(780110/91, 282410/90, 8507x0)",
        "pos": (COL_MFG, TRADE_ROW),
        "chain_key": None, "kind": "trade",
        "formula": (r"\Delta_{\mathrm{feed}} = \sum\mathrm{imp}_{\mathrm{FEED\,HS}} - \sum\mathrm{exp}_{\mathrm{FEED\,HS}}"
                    r"\\ \Delta_{\mathrm{batt}} = \mathrm{imp}_{8507\mathrm{x}0} - \mathrm{exp}_{8507\mathrm{x}0}"),
        "variables_keys": [],
        "assumptions": "FEED enters the refined pool; finished batteries (850710 + 850720) "
                       "skip MFG and add directly to installs.",
        "_attach": "mfg_F",
        "_chain_pair": None,  # composite — computed inline in _node_volume_at_year
    },
    {
        "id": "primary_usgs", "label": "Primary Pb (USGS)\n(exogenous, formal)",
        "pos": (COL_REFINE + 0.5, TRADE_ROW + 0.3),
        "chain_key": "REFINE_PRIMARY", "kind": "trade",
        "formula": r"\mathrm{REFINE\_PRIMARY}_{\mathrm{USGS}}",
        "variables_keys": [],
        "assumptions": "USGS-reported primary refined Pb. Treated as formal. Enters "
                       "the refined pool BEFORE MFG (not at smelt — the PDF "
                       "shows it conceptually near SMELT, but in code it joins "
                       "the refined pool, which is mathematically equivalent).",
        "_attach": "mfg_F",
    },
]

# ---- anchors (not flows, just references) ----------------------------------

ANCHOR_NODES = [
    {
        "id": "usgs_anchor", "label": "USGS = anchor\nfor FORMAL refined SEC",
        "pos": (COL_REFINE, ANCHOR_ROW),
        "chain_key": None, "kind": "anchor",
        "formula": r"\mathrm{REFINE\_SEC}_F \;\ge\; \mathrm{USGS}_{\mathrm{sec}}",
        "variables_keys": [],
        "assumptions": "One-sided floor: chain must produce at least USGS secondary "
                       "from the formal lane. Overshoot is expected and represents "
                       "the implied unrecorded refined Pb.",
    },
    {
        "id": "nonbatt", "label": "Non-battery uses\n(1 − β)",
        "pos": (COL_MFG - 0.5, ANCHOR_ROW),
        "chain_key": None, "kind": "anchor",
        "formula": r"\mathrm{NB} = \mathrm{refined\_total}\cdot(1-\beta)\,\cdot\,(\text{never tracked further})",
        "variables_keys": ["beta"],
        "assumptions": "(1-β) of refined-feed is allocated to non-battery uses (paints, "
                       "alloys, ammunition, etc.). Not tracked further in this model.",
    },
    {
        "id": "stock", "label": "In service / Stock\nΔStock + RETIRE",
        "pos": (COL_STOCK, ANCHOR_ROW + 0.8),
        "chain_key": None, "kind": "anchor",
        "formula": r"\mathrm{stock}_{\mathrm{eff}}(t) = k \cdot \mathrm{stock}(t)",
        "variables_keys": ["k", "tau"],
        "assumptions": "Stock series from `India_Installed` (USAID-derived). "
                       "Closed loop: Installation → Stock → retire → Collection.",
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
    ("usgs_anchor", "refine_F", "anchor"),
    ("nonbatt",     "mfg_F",    "anchor"),

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
        # Build a multi-line label: name + (lane η if applicable) + volume
        eta_line = ""
        if kind == "formal":
            mapping = {"break_F": "eta_break_F", "smelt_F": "eta_smelt_F",
                       "refine_F": "eta_refine_F", "mfg_F": "eta_mfg_F"}
            k_ = mapping.get(n["id"])
            if k_:
                eta_line = f"η_F = {etas[k_]:.2f}"
        elif kind == "informal":
            mapping = {"break_I": "eta_break_I", "smelt_I": "eta_smelt_I",
                       "refine_I": "eta_refine_I", "mfg_I": "eta_mfg_I"}
            k_ = mapping.get(n["id"])
            if k_:
                eta_line = f"η_I = {etas[k_]:.2f}"
        body = n["label"]
        if eta_line:
            body = f"{body}<br><i>{eta_line}</i>"
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
# streamlit-flow library — try variants
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
    series = [
        ("COLLECT",            chain["COLLECT"],          "#FBC02D", "solid"),
        ("BREAK_total",        chain["BREAK_total"],      "#9467bd", "solid"),
        ("SMELT_total",        chain["SMELT_total"],      "#8c564b", "solid"),
        ("REFINE_SEC_F",       chain["REFINE_SEC_F"],     "#d62728", "solid"),
        ("USGS_sec (anchor)",  arr["sec_usgs"],           "#d62728", "dot"),
        ("MFG_total",          chain["MFG_total"],        "#2ca02c", "solid"),
        ("INSTALL_implied",    chain["INSTALL_implied"],  "#000000", "solid"),
        ("INSTALL_target",     chain["INSTALL_target"],   "#000000", "dot"),
    ]
    fig = go.Figure()
    for name, vec, color, dash in series:
        fig.add_trace(go.Scatter(
            x=years, y=vec, mode="lines+markers", name=name,
            line=dict(color=color, width=2, dash=dash),
            hovertemplate=f"{name}<br>%{{x}}: %{{y:,.0f}} t Pb<extra></extra>",
        ))
    fig.update_layout(
        height=380, margin=dict(l=40, r=20, t=30, b=40),
        xaxis_title="Year", yaxis_title="t Pb / yr",
        legend=dict(orientation="h", y=-0.20, x=0.0),
        title="Major process steps — fit window",
    )
    st.plotly_chart(fig, use_container_width=True, theme="streamlit")


# ============================================================================
# Tab entry point
# ============================================================================

def render() -> None:
    state = compute_state()
    chain = state["chain"]; arr = state["arr"]

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

    # Two-column layout: diagram | detail
    diag_col, detail_col = st.columns([3, 2])

    with diag_col:
        lib_name, ns = _try_flow_lib()
        selected_id = None
        rendered = False
        if lib_name == "streamlit_flow":
            selected_id, rendered = _flow_diagram_streamlit_flow(state, year, ns)
        elif lib_name == "streamlit_flow_component":
            selected_id, rendered = _flow_diagram_chrisdelclea(state, year, ns)
        if not rendered:
            if lib_name is None:
                st.info(
                    "Static Plotly diagram. To switch to an interactive React-Flow "
                    "view, install `streamlit-flow-swc` (preferred) or "
                    "`streamlit-flow-component`. The Plotly diagram below matches "
                    "the PDF topology either way.",
                    icon="ℹ️",
                )
            fig = _plotly_diagram(state, year)
            st.plotly_chart(fig, use_container_width=True, theme="streamlit",
                            config={"displayModeBar": False})

    with detail_col:
        # Selectbox always works regardless of click events
        node_choices = [n["id"] for n in NODES]
        default_idx = (node_choices.index(selected_id)
                       if (selected_id and selected_id in node_choices)
                       else node_choices.index("install_implied"))
        chosen = st.selectbox(
            "Node detail", options=node_choices,
            index=default_idx, key="diagram_node",
            format_func=lambda i: next(n["label"].replace("\n", " — ")
                                       for n in NODES if n["id"] == i),
        )
        node = next(n for n in NODES if n["id"] == chosen)
        _render_node_detail(node, state)

    st.divider()
    _render_line_graph(state)
