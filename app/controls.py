"""Tab 2 — user-editable inputs.

Stock + segments + k + τ-override + the four formal-share φ values. Every
value is written to st.session_state so Tab 1 (the diagram) and Tab 3 (the
readme) read the same numbers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from india_model.model_v4 import tau_eff, fit_growth_rate
from india_model.model_v5_parallel import REF_PHI, PHI_FLOORS, phi_is_ordered

from app.state import load_raw_csv, load_segments_df


def render() -> None:
    """Render the controls tab. Writes to st.session_state."""
    st.markdown(
        "### Inputs — stock, segments, k, τ, and the four formal shares (φ)"
    )
    st.caption(
        "These are the **state** dials of the dashboard. Process parameters "
        "(β, γ, η) live in the sidebar. Edit anything here and the flow "
        "diagram in Tab 1 updates."
    )

    df_csv = load_raw_csv()

    # ------------------------------------------------------------------
    # k slider (default 1.0)
    # ------------------------------------------------------------------
    st.markdown("##### Stock multiplier (k_stock)")
    st.slider(
        "k_stock — applied to every stock-derived flow",
        min_value=0.40, max_value=1.50, step=0.01,
        value=float(st.session_state.get("k_stock", 1.0)),
        key="k_stock",
        help="Default 1.0. Slide to explore how lower/higher reported stock "
             "would change every downstream flow.",
    )

    # ------------------------------------------------------------------
    # Stock table editor + g
    # ------------------------------------------------------------------
    st.markdown("##### Lead in service (stock_total_t_pb, t Pb)")
    default_stock = df_csv[["year", "stock_total_t_pb"]].copy()
    default_stock["year"] = default_stock["year"].astype(int)
    edited_stock = st.data_editor(
        st.session_state.get("user_stock", default_stock),
        num_rows="fixed",
        hide_index=True,
        use_container_width=True,
        key="stock_editor",
        column_config={
            "year": st.column_config.NumberColumn("Year", disabled=True, format="%d"),
            "stock_total_t_pb": st.column_config.NumberColumn(
                "Total Pb in service (t)", min_value=0.0, format="%.0f",
            ),
        },
    )
    edited_stock = edited_stock.dropna(subset=["stock_total_t_pb"]).reset_index(drop=True)
    if len(edited_stock) >= 3:
        st.session_state["user_stock"] = edited_stock
        try:
            g_val = float(fit_growth_rate(
                edited_stock["stock_total_t_pb"].to_numpy(dtype=float),
                edited_stock["year"].to_numpy(dtype=float),
            ))
            st.caption(f"Fitted **g = {g_val:.4f} / yr** (log-linear regression on the table).")
        except Exception as e:
            st.error(f"Could not fit growth rate: {e}")
    else:
        st.error(f"Stock table needs ≥ 3 years (currently {len(edited_stock)}).")

    # ------------------------------------------------------------------
    # Segments table editor + τ_eff + override toggle
    # ------------------------------------------------------------------
    st.markdown("##### Battery segments → τ_eff (harmonic mean)")
    default_segs = load_segments_df()
    edited_segs = st.data_editor(
        st.session_state.get("user_segments", default_segs),
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key="segments_editor",
        column_config={
            "segment":        st.column_config.TextColumn("Segment"),
            "stock_share":    st.column_config.NumberColumn(
                "Stock share", min_value=0.0, max_value=1.0, step=0.01, format="%.2f",
            ),
            "lifetime_years": st.column_config.NumberColumn(
                "Lifetime (yrs)", min_value=0.5, step=0.5, format="%.1f",
            ),
        },
    )
    edited_segs = edited_segs.dropna(subset=["stock_share", "lifetime_years"]).reset_index(drop=True)
    share_sum = float(edited_segs["stock_share"].sum()) if len(edited_segs) else 0.0
    if len(edited_segs) and np.isclose(share_sum, 1.0, atol=1e-6):
        st.session_state["user_segments"] = edited_segs
        tau_seg = float(tau_eff(edited_segs))
        st.caption(f"**τ_eff = {tau_seg:.2f} yr** (harmonic mean of segments).")

        cols = st.columns([2, 5])
        with cols[0]:
            st.toggle(
                "Override τ with slider",
                value=bool(st.session_state.get("tau_override", False)),
                key="tau_override",
                help=f"Off: use τ_eff = {tau_seg:.2f} yr. "
                     "On: slider value replaces it everywhere.",
            )
        with cols[1]:
            if st.session_state.get("tau_override", False):
                st.slider(
                    "τ override (yrs)",
                    min_value=2.0, max_value=12.0, step=0.05,
                    value=float(st.session_state.get("tau_slider", tau_seg)),
                    key="tau_slider",
                )
    else:
        st.error(f"Segments must sum to 1.0 (currently {share_sum:.4f}).")

    # ------------------------------------------------------------------
    # φ inputs — USAID floors
    # ------------------------------------------------------------------
    st.markdown("##### Formal shares (φ) — USAID floors")
    st.caption(
        "Per-stage lower bounds reflect USAID's view that formal share is "
        "high and rises down the chain. "
        f"Floors: φ_smelt ≥ {PHI_FLOORS['phi_smelt_f']:.2f}, "
        f"φ_refine ≥ {PHI_FLOORS['phi_refine_f']:.2f}, "
        f"φ_mfg ≥ {PHI_FLOORS['phi_mfg_f']:.2f}. "
        "Ordering (break < smelt < refine < mfg < 1) is enforced as a warning."
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.number_input("φ_break_f",
            PHI_FLOORS["phi_break_f"], 0.99, REF_PHI["phi_break_f"], 0.01,
            key="phi_break_f")
    with c2:
        st.number_input("φ_smelt_f",
            PHI_FLOORS["phi_smelt_f"], 0.99, REF_PHI["phi_smelt_f"], 0.01,
            key="phi_smelt_f")
    with c3:
        st.number_input("φ_refine_f",
            PHI_FLOORS["phi_refine_f"], 0.99, REF_PHI["phi_refine_f"], 0.01,
            key="phi_refine_f")
    with c4:
        st.number_input("φ_mfg_f",
            PHI_FLOORS["phi_mfg_f"], 0.99, REF_PHI["phi_mfg_f"], 0.01,
            key="phi_mfg_f")

    phi_d = {
        "phi_break_f":  st.session_state.get("phi_break_f"),
        "phi_smelt_f":  st.session_state.get("phi_smelt_f"),
        "phi_refine_f": st.session_state.get("phi_refine_f"),
        "phi_mfg_f":    st.session_state.get("phi_mfg_f"),
    }
    if not phi_is_ordered(phi_d):
        st.warning(
            f"Ordering violated: need φ_break ({phi_d['phi_break_f']:.2f}) < "
            f"φ_smelt ({phi_d['phi_smelt_f']:.2f}) < "
            f"φ_refine ({phi_d['phi_refine_f']:.2f}) < "
            f"φ_mfg ({phi_d['phi_mfg_f']:.2f}) < 1. "
            "Tab 1's crossover indicators will flag where this hurts."
        )
