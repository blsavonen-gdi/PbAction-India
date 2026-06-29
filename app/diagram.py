"""Tab 1 — system flow diagram + line graph.

The diagram uses streamlit-flow-component when available; if the library is
missing or fails, we fall back to a Plotly node-and-arrow diagram so the tab
still loads. Either way, a side panel shows the equation + per-year values
+ assumptions for the currently selected node, driven by both click events
(when the library reports them) and a selectbox (always available).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.state import compute_state


# ---- Node catalogue --------------------------------------------------------
# Each node has:
#   id          : short slug used as the flow-component id
#   label       : display label
#   pos         : (col, row) grid coords; converted to pixel x/y at render
#   chain_key   : key in chain dict whose per-year array gives the node's volume
#                 (None for nodes that aren't a flow, e.g. anchors)
#   formula     : LaTeX equation rendered in the side panel
#   variables   : list of (symbol, description) shown as a table
#   assumptions : free-text notes
#   kind        : "core" | "trade" | "anchor"  (just for styling)
#
# Layout: 6 columns × 3 rows. Formal lane top, shared/anchors middle, informal
# lane bottom. Trade nodes hang above/below the lane they attach to.

NODES = [
    # ---------- col 0 : stock / retire / collect ----------------------
    {
        "id": "stock", "label": "STOCK (t Pb)", "pos": (0, 1),
        "chain_key": "eff_stock", "kind": "anchor",
        "formula": r"\mathrm{stock}_{\mathrm{eff}}(t) = k \cdot \mathrm{stock}(t)",
        "variables": [
            ("k", "stock multiplier (Tab 2 slider; default 1.0)"),
            ("stock(t)", "user-edited Pb-in-service totals (Tab 2)"),
        ],
        "assumptions": "Stock series is from `India_Installed` (commit 119fc72), "
                       "smoothed 3-yr centered rolling.",
    },
    {
        "id": "retire", "label": "RETIRE", "pos": (1, 1),
        "chain_key": "RETIRE", "kind": "core",
        "formula": r"\mathrm{RETIRE}(t) = \mathrm{stock}_{\mathrm{eff}}(t) \cdot r(g, \tau)",
        "variables": [
            ("r", "retirement rate = g / (e^{gτ} − 1)"),
            ("g", "log-linear stock growth rate"),
            ("τ", "effective lifetime (harmonic mean of segments)"),
        ],
        "assumptions": "Growth-corrected retirement; converges to 1/τ as g→0.",
    },
    {
        "id": "collect", "label": "COLLECT", "pos": (2, 1),
        "chain_key": "COLLECT", "kind": "core",
        "formula": r"\mathrm{COLLECT} = \gamma \cdot \mathrm{RETIRE}",
        "variables": [
            ("γ", "total collection rate (sidebar, default 0.98)"),
        ],
        "assumptions": "Single shared pool. The formal/informal split happens "
                       "at BREAK, not here.",
    },

    # ---------- col 3 : BREAK lanes + used trade -----------------------
    {
        "id": "used_trade", "label": "TRADE\nimp/exp 854810\n(formal-only)", "pos": (3, 0),
        "chain_key": None, "kind": "trade",
        "formula": r"\Delta_{\mathrm{used}} = \mathrm{imp}_{854810} - \mathrm{exp}_{854810}",
        "variables": [
            ("imp/exp_854810", "used-battery trade in t Pb content"),
        ],
        "assumptions": "USAID: external trade is virtually all formal. Imported "
                       "used batteries flow through legal customs into formal "
                       "breakers; informal lane has no trade.",
    },
    {
        "id": "break_F", "label": "BREAK_F (formal)", "pos": (3, 1),
        "chain_key": "out_break_F", "kind": "core",
        "formula": (r"\mathrm{in\_break}_F = \mathrm{COLLECT}\cdot\phi_{\mathrm{break}}^f + \Delta_{\mathrm{used}}"
                    r"\\ \mathrm{out\_break}_F = \mathrm{in\_break}_F \cdot \delta \cdot \eta_{\mathrm{break}}^F"),
        "variables": [
            ("φ_break_f", "formal share of breaking (Tab 2; default 0.70)"),
            ("δ", "Pb at end-of-life (sidebar; default 0.95)"),
            ("η_break_F", "formal breaking recovery (sidebar; default 0.95)"),
        ],
        "assumptions": "Used-battery trade attaches to the formal break input only.",
    },
    {
        "id": "break_I", "label": "BREAK_I (informal)", "pos": (3, 2),
        "chain_key": "out_break_I", "kind": "core",
        "formula": (r"\mathrm{in\_break}_I = \mathrm{COLLECT}\cdot(1-\phi_{\mathrm{break}}^f)"
                    r"\\ \mathrm{out\_break}_I = \mathrm{in\_break}_I \cdot \delta \cdot \eta_{\mathrm{break}}^I"),
        "variables": [
            ("η_break_I", "informal breaking recovery (sidebar; default 0.70)"),
        ],
        "assumptions": "Informal lane is purely domestic — no trade flows in or out.",
    },

    # ---------- col 4 : SMELT lanes + scrap trade ----------------------
    {
        "id": "scrap_trade", "label": "TRADE\nimp/exp 780200\n(formal-only)", "pos": (4, 0),
        "chain_key": None, "kind": "trade",
        "formula": r"\Delta_{\mathrm{scrap}} = \mathrm{imp}_{780200} - \mathrm{exp}_{780200}",
        "variables": [
            ("imp/exp_780200", "lead scrap trade (HS 780200, η_conv = 0.97)"),
        ],
        "assumptions": "Attaches to the formal scrap pool only.",
    },
    {
        "id": "smelt_F", "label": "SMELT_F", "pos": (4, 1),
        "chain_key": "out_smelt_F", "kind": "core",
        "formula": (r"\mathrm{scrap\_total} = \mathrm{out\_break}_F + \mathrm{out\_break}_I + \Delta_{\mathrm{scrap}}"
                    r"\\ \mathrm{out\_smelt}_F = (\mathrm{scrap\_total}\cdot\phi_{\mathrm{smelt}}^f)\cdot\eta_{\mathrm{smelt}}^F"),
        "variables": [
            ("φ_smelt_f", "formal share of smelting (Tab 2; default 0.80)"),
            ("η_smelt_F", "formal smelting recovery (sidebar; default 0.97)"),
        ],
        "assumptions": "Implied crossover at this boundary: in_smelt_F − out_break_F.",
    },
    {
        "id": "smelt_I", "label": "SMELT_I", "pos": (4, 2),
        "chain_key": "out_smelt_I", "kind": "core",
        "formula": r"\mathrm{out\_smelt}_I = (\mathrm{scrap\_total}\cdot(1-\phi_{\mathrm{smelt}}^f))\cdot\eta_{\mathrm{smelt}}^I",
        "variables": [
            ("η_smelt_I", "informal smelting recovery (sidebar; default 0.60)"),
        ],
        "assumptions": "No trade flows.",
    },

    # ---------- col 5 : REFINE lanes + crude trade + USGS anchor -------
    {
        "id": "crude_trade", "label": "TRADE\nimp/exp 780199\n(formal-only)", "pos": (5, 0),
        "chain_key": None, "kind": "trade",
        "formula": r"\Delta_{\mathrm{crude}} = \mathrm{imp}_{780199} - \mathrm{exp}_{780199}",
        "variables": [
            ("imp/exp_780199", "lead, unrefined other (HS 780199, η_conv = 0.95)"),
        ],
        "assumptions": "Attaches at the formal crude pool between SMELT and REFINE.",
    },
    {
        "id": "refine_F", "label": "REFINE_F\n(USGS anchor)", "pos": (5, 1),
        "chain_key": "REFINE_SEC_F", "kind": "core",
        "formula": (r"\mathrm{crude\_total} = \mathrm{out\_smelt}_F + \mathrm{out\_smelt}_I + \Delta_{\mathrm{crude}}"
                    r"\\ \mathrm{REFINE\_SEC}_F = (\mathrm{crude\_total}\cdot\phi_{\mathrm{refine}}^f)\cdot\eta_{\mathrm{refine}}^F"),
        "variables": [
            ("φ_refine_f", "formal share of refining (Tab 2; default 0.90)"),
            ("η_refine_F", "formal refining recovery (sidebar; default 0.99)"),
        ],
        "assumptions": "**USGS secondary anchors REFINE_SEC_F as a one-sided floor.** "
                       "Overshoot is expected and represents implied unrecorded refining; "
                       "only undershoot is a failure.",
    },
    {
        "id": "refine_I", "label": "REFINE_I", "pos": (5, 2),
        "chain_key": "REFINE_SEC_I", "kind": "core",
        "formula": r"\mathrm{REFINE\_SEC}_I = (\mathrm{crude\_total}\cdot(1-\phi_{\mathrm{refine}}^f))\cdot\eta_{\mathrm{refine}}^I",
        "variables": [
            ("η_refine_I", "informal refining recovery (sidebar; default 0.95)"),
        ],
        "assumptions": "Informal refined Pb is NOT counted by USGS — it would be the "
                       "explanation for the refine overshoot in the formal lane.",
    },

    # ---------- col 6 : refined pool + primary + feed -----------------
    {
        "id": "primary_usgs", "label": "PRIMARY (USGS)", "pos": (6, 0),
        "chain_key": "REFINE_PRIMARY", "kind": "trade",
        "formula": r"\mathrm{REFINE\_PRIMARY}_{\mathrm{USGS}}",
        "variables": [
            ("primary_pb_t_usgs", "USGS-reported primary refined Pb, per year"),
        ],
        "assumptions": "Treated as formal. Enters the refined pool before MFG.",
    },
    {
        "id": "feed_trade", "label": "TRADE FEED\n(780110/91, 282410/90)", "pos": (6, 2),
        "chain_key": None, "kind": "trade",
        "formula": r"\Delta_{\mathrm{feed}} = \sum \mathrm{imp}_{\mathrm{feed\,HS}} - \sum \mathrm{exp}_{\mathrm{feed\,HS}}",
        "variables": [
            ("FEED_HS", "780110, 780191, 282410, 282490 — refined-equivalents subject to β"),
        ],
        "assumptions": "Formal trade only. Oxides (282410/282490) stay in FEED and "
                       "remain subject to β.",
    },

    # ---------- col 7 : MFG lanes + parts trade -----------------------
    {
        "id": "parts_trade", "label": "TRADE PARTS\n(850790, formal)", "pos": (7, 0),
        "chain_key": None, "kind": "trade",
        "formula": r"\mathrm{NET\_PARTS} = \mathrm{imp}_{850790} - \mathrm{exp}_{850790}",
        "variables": [
            ("imp/exp_850790", "battery parts trade (HS 850790, η_conv = 0.80)"),
        ],
        "assumptions": "Battery parts are battery-committed: route to formal MFG with "
                       "η_mfg_F only, **bypassing β**.",
    },
    {
        "id": "mfg_F", "label": "MFG_F", "pos": (7, 1),
        "chain_key": "MFG_F", "kind": "core",
        "formula": (r"\mathrm{refined\_total} = \mathrm{REFINE\_SEC}_F + \mathrm{REFINE\_SEC}_I"
                    r" + \mathrm{REFINE\_PRIMARY}_{\mathrm{USGS}} + \Delta_{\mathrm{feed}}"
                    r"\\ \mathrm{MFG}_F = (\mathrm{refined\_total}\cdot\phi_{\mathrm{mfg}}^f)\cdot\beta\cdot\eta_{\mathrm{mfg}}^F"
                    r"\\ \qquad + \max(0, \mathrm{NET\_PARTS})\cdot\eta_{\mathrm{mfg}}^F"),
        "variables": [
            ("φ_mfg_f", "formal share of mfg (Tab 2; default 0.95)"),
            ("β", "battery share of refined-Pb demand (sidebar; default 0.86)"),
            ("η_mfg_F", "formal mfg recovery (sidebar; default 0.98)"),
        ],
        "assumptions": "Battery parts bypass β. Oxides stay subject to β.",
    },
    {
        "id": "mfg_I", "label": "MFG_I", "pos": (7, 2),
        "chain_key": "MFG_I", "kind": "core",
        "formula": r"\mathrm{MFG}_I = (\mathrm{refined\_total}\cdot(1-\phi_{\mathrm{mfg}}^f))\cdot\beta\cdot\eta_{\mathrm{mfg}}^I",
        "variables": [
            ("η_mfg_I", "informal mfg recovery (sidebar; default 0.95)"),
        ],
        "assumptions": "No parts bypass for the informal lane; β applies fully.",
    },

    # ---------- col 8 : install ---------------------------------------
    {
        "id": "batt_trade", "label": "TRADE BATTERIES\n(850710 + 850720)", "pos": (8, 0),
        "chain_key": None, "kind": "trade",
        "formula": r"\Delta_{\mathrm{batt}} = \mathrm{imp}_{850710+850720} - \mathrm{exp}_{850710+850720}",
        "variables": [
            ("imp/exp_8507x0", "finished-battery trade (HS 850710 SLI + 850720 industrial)"),
        ],
        "assumptions": "Skips MFG entirely; adds directly to installs.",
    },
    {
        "id": "install_implied", "label": "INSTALL_implied\n(supply)", "pos": (8, 1),
        "chain_key": "INSTALL_implied", "kind": "core",
        "formula": r"\mathrm{INSTALL\_implied} = \mathrm{MFG}_F + \mathrm{MFG}_I + \Delta_{\mathrm{batt}}",
        "variables": [
            ("MFG_F + MFG_I", "both lanes' mfg output rejoin at install"),
            ("Δbatt", "finished-battery net trade"),
        ],
        "assumptions": "The lanes rejoin here — both formal and informal batteries are installed.",
    },
    {
        "id": "install_target", "label": "INSTALL_target\n(stock-derived)", "pos": (8, 2),
        "chain_key": "INSTALL_target", "kind": "anchor",
        "formula": r"\mathrm{INSTALL\_target} = \Delta\mathrm{Stock} + \mathrm{RETIRE}",
        "variables": [
            ("ΔStock", "year-on-year stock change at k_stock"),
            ("RETIRE", "from the retirement engine"),
        ],
        "assumptions": "INSTALL_implied = INSTALL_target is the install anchor (two-sided).",
    },
]


# ---- Edges (logical, not styled) -------------------------------------------

EDGES = [
    ("stock", "retire"),
    ("retire", "collect"),
    ("collect", "break_F"),  ("collect", "break_I"),
    ("used_trade", "break_F"),
    ("break_F", "smelt_F"),  ("break_F", "smelt_I"),
    ("break_I", "smelt_F"),  ("break_I", "smelt_I"),
    ("scrap_trade", "smelt_F"),
    ("smelt_F", "refine_F"), ("smelt_F", "refine_I"),
    ("smelt_I", "refine_F"), ("smelt_I", "refine_I"),
    ("crude_trade", "refine_F"),
    ("refine_F", "mfg_F"),   ("refine_F", "mfg_I"),
    ("refine_I", "mfg_F"),   ("refine_I", "mfg_I"),
    ("primary_usgs", "mfg_F"),
    ("feed_trade",   "mfg_F"), ("feed_trade", "mfg_I"),
    ("parts_trade",  "mfg_F"),
    ("mfg_F", "install_implied"),
    ("mfg_I", "install_implied"),
    ("batt_trade", "install_implied"),
    ("install_target", "install_implied"),  # dotted, comparison
]


# ---- Helpers ---------------------------------------------------------------

def _node_volume_at_year(node: dict, chain: dict, arr: dict, year: int) -> float | None:
    """Return the node's per-year volume in t Pb at `year`, or None if N/A."""
    if node["chain_key"] is None:
        # Trade nodes don't have a single chain key; compute on the fly.
        idx = int(np.where(arr["year"] == year)[0][0])
        sid = node["id"]
        if sid == "used_trade":
            return float(arr["imp_used"][idx] - arr["exp_used"][idx])
        if sid == "scrap_trade":
            return float(arr["imp_scrap"][idx] - arr["exp_scrap"][idx])
        if sid == "crude_trade":
            return float(arr["imp_crude"][idx] - arr["exp_crude"][idx])
        if sid == "feed_trade":
            return float(arr["imp_feed"][idx] - arr["exp_feed"][idx])
        if sid == "parts_trade":
            return float(arr["imp_parts"][idx] - arr["exp_parts"][idx])
        if sid == "batt_trade":
            return float(arr["imp_batt"][idx] - arr["exp_batt"][idx])
        return None
    arr_vec = chain.get(node["chain_key"])
    if arr_vec is None:
        return None
    idx = int(np.where(arr["year"] == year)[0][0])
    return float(arr_vec[idx])


def _fmt_kt(x: float | None) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x / 1000:,.1f} kt"


# ---- Plotly fallback diagram -----------------------------------------------

def _plotly_diagram(chain: dict, arr: dict, year: int) -> go.Figure:
    """Static node-and-arrow diagram. Used when streamlit-flow-component is
    unavailable. Nodes are placed on the (col, row) grid; arrows are drawn
    via plotly annotations."""
    color_by_kind = {"core": "#1f77b4", "trade": "#ff7f0e", "anchor": "#2ca02c"}
    xs, ys, texts, colors, ids = [], [], [], [], []
    pos_by_id = {}
    for node in NODES:
        col, row = node["pos"]
        x, y = col * 1.0, -row * 1.0
        vol = _node_volume_at_year(node, chain, arr, year)
        label = node["label"].replace("\n", "<br>")
        vol_str = _fmt_kt(vol) if vol is not None else ""
        text = f"<b>{label}</b><br>{vol_str}"
        xs.append(x); ys.append(y); texts.append(text)
        colors.append(color_by_kind.get(node["kind"], "#888"))
        ids.append(node["id"])
        pos_by_id[node["id"]] = (x, y)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, text=texts, mode="markers+text",
        marker=dict(size=46, color=colors, line=dict(color="#222", width=1)),
        textfont=dict(size=10, color="white"),
        textposition="middle center",
        hovertext=[f"id: {i}" for i in ids],
        hoverinfo="text",
        customdata=ids, showlegend=False,
    ))

    for src, tgt in EDGES:
        if src not in pos_by_id or tgt not in pos_by_id:
            continue
        x0, y0 = pos_by_id[src]; x1, y1 = pos_by_id[tgt]
        dash = "dot" if (src == "install_target") else "solid"
        fig.add_annotation(
            x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowsize=1.0, arrowwidth=1.2,
            arrowcolor="#888", standoff=18, startstandoff=18, opacity=0.55,
        )
        if dash == "dot":
            fig.add_annotation(
                x=(x0+x1)/2, y=(y0+y1)/2, xref="x", yref="y",
                text="compare", showarrow=False, font=dict(size=9, color="#666"),
            )

    fig.update_layout(
        height=520, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(visible=False, range=[-0.5, 9]),
        yaxis=dict(visible=False, range=[-2.7, 0.7]),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ---- streamlit-flow-component primary diagram ------------------------------

def _flow_component_diagram(chain: dict, arr: dict, year: int):
    """Try to render with streamlit-flow-component. Return (selected_id, ok).
    ok=False means the import or render failed; caller should fall back.
    """
    try:
        from streamlit_flow_component import st_flow  # type: ignore
    except Exception:
        return None, False

    color_by_kind = {"core": "#1f77b4", "trade": "#ff7f0e", "anchor": "#2ca02c"}
    nodes, edges = [], []
    for node in NODES:
        col, row = node["pos"]
        vol = _node_volume_at_year(node, chain, arr, year)
        vol_str = _fmt_kt(vol) if vol is not None else ""
        label = node["label"].replace("\n", " — ")
        nodes.append({
            "id":    node["id"],
            "type":  "default",
            "data":  {"label": f"{label}\n{vol_str}"},
            "position": {"x": col * 160, "y": row * 110},
            "style": {
                "background": color_by_kind.get(node["kind"], "#888"),
                "color": "white",
                "borderRadius": "8px",
                "padding": "8px",
                "width": 150,
                "whiteSpace": "pre-wrap",
                "fontSize": "11px",
            },
        })
    for src, tgt in EDGES:
        edges.append({
            "id": f"{src}-{tgt}",
            "source": src,
            "target": tgt,
            "animated": src in ("collect", "break_F", "smelt_F", "refine_F", "mfg_F"),
            "type": "smoothstep",
            "style": {"strokeDasharray": "4 4"} if src == "install_target" else None,
        })
    try:
        result = st_flow(nodes=nodes, edges=edges, key="india_flow",
                         height=560, fit_view=True)
    except Exception:
        return None, False
    # Result shape varies by version; try to extract a selected node id.
    selected = None
    try:
        if isinstance(result, dict) and "selected" in result:
            selected = result["selected"]
        elif hasattr(result, "selected"):
            selected = result.selected
    except Exception:
        selected = None
    return selected, True


# ---- Side panel ------------------------------------------------------------

def _render_node_detail(node: dict, chain: dict, arr: dict) -> None:
    """Render the right-side detail for a node: formula + per-year vols + assumptions."""
    st.markdown(f"### {node['label'].replace(chr(10), ' — ')}")
    st.caption(f"id: `{node['id']}` · kind: `{node['kind']}`")

    st.markdown("**Formula**")
    st.latex(node["formula"])

    st.markdown("**Variables**")
    var_df = pd.DataFrame(node["variables"], columns=["symbol", "meaning"])
    st.dataframe(var_df, hide_index=True, use_container_width=True)

    st.markdown("**Per-year volume (t Pb)**")
    years = arr["year"]
    vols = [_node_volume_at_year(node, chain, arr, int(y)) for y in years]
    val_df = pd.DataFrame({
        "Year":  [int(y) for y in years],
        "Volume (t Pb)": [None if v is None else round(v, 0) for v in vols],
    })
    st.dataframe(val_df, hide_index=True, use_container_width=True)

    st.markdown("**Assumptions / notes**")
    st.markdown(node["assumptions"])


# ---- Line graph below the diagram ------------------------------------------

def _render_line_graph(chain: dict, arr: dict) -> None:
    """Major process steps over the fit window — supply-chain time series."""
    years = arr["year"]
    series = [
        ("COLLECT",            chain["COLLECT"],          "#1f77b4"),
        ("BREAK_total",        chain["BREAK_total"],      "#9467bd"),
        ("SMELT_total",        chain["SMELT_total"],      "#8c564b"),
        ("REFINE_SEC_F",       chain["REFINE_SEC_F"],     "#d62728"),
        ("USGS_sec (anchor)",  arr["sec_usgs"],           "#d62728"),
        ("MFG_total",          chain["MFG_total"],        "#2ca02c"),
        ("INSTALL_implied",    chain["INSTALL_implied"],  "#000000"),
        ("INSTALL_target",     chain["INSTALL_target"],   "#000000"),
    ]
    fig = go.Figure()
    for name, arr_vec, color in series:
        dash = "dot" if name in ("USGS_sec (anchor)", "INSTALL_target") else "solid"
        fig.add_trace(go.Scatter(
            x=years, y=arr_vec, mode="lines+markers",
            name=name,
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


# ---- Tab 1 entry point -----------------------------------------------------

def render() -> None:
    state = compute_state()
    chain = state["chain"]
    arr   = state["arr"]

    st.markdown("### System flow — parallel formal/informal chain")
    st.caption(
        "Each node shows its volume for the year selected below. **Click** "
        "a node (or pick one from the dropdown) to see its formula, variables, "
        "and assumptions in the right-hand panel. Edit inputs in Tab 2 or in "
        "the sidebar to change the numbers."
    )

    # Year selector
    years = arr["year"].astype(int).tolist()
    cols = st.columns([2, 6])
    with cols[0]:
        year = int(st.selectbox(
            "Year", options=years,
            index=len(years) - 1,
            key="diagram_year",
            help="Volumes in the diagram nodes are for this year.",
        ))

    # Layout: diagram on left, detail panel on right
    diag_col, detail_col = st.columns([3, 2])

    with diag_col:
        selected_id, ok = _flow_component_diagram(chain, arr, year)
        if not ok:
            st.info(
                "Falling back to the static Plotly diagram. "
                "`streamlit-flow-component` is not installed or failed to "
                "render. Run `pip install streamlit-flow-component` to "
                "switch to the interactive React Flow view.",
                icon="ℹ️",
            )
            fig = _plotly_diagram(chain, arr, year)
            st.plotly_chart(fig, use_container_width=True, theme="streamlit",
                            config={"displayModeBar": False})

    with detail_col:
        # Selectbox-based picker (always works, regardless of click events)
        node_choices = [n["id"] for n in NODES]
        default_idx = (node_choices.index(selected_id)
                       if selected_id in node_choices else node_choices.index("install_implied"))
        chosen = st.selectbox(
            "Node detail", options=node_choices,
            index=default_idx, key="diagram_node",
            format_func=lambda i: next(n["label"].replace("\n", " — ")
                                       for n in NODES if n["id"] == i),
        )
        node = next(n for n in NODES if n["id"] == chosen)
        _render_node_detail(node, chain, arr)

    st.divider()
    _render_line_graph(chain, arr)
