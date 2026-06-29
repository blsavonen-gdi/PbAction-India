"""Sidebar (β, γ, all η). The slide-out menu of process-side parameters."""

from __future__ import annotations

import streamlit as st

from india_model.model_v5_parallel import ETA_DEFAULTS, BETA_DEFAULT, GAMMA_TOTAL


def render() -> None:
    """Sidebar widgets — write values directly into st.session_state."""
    with st.sidebar:
        st.markdown("### Process parameters")
        st.caption(
            "These are the **chain-physics** dials: battery share, total "
            "collection, and the per-stage efficiencies of the formal and "
            "informal lanes. Editing here updates every tab."
        )
        st.markdown("**β / γ**")
        st.number_input(
            "β — battery share of refined-Pb demand",
            min_value=0.30, max_value=0.99, step=0.01,
            value=float(st.session_state.get("beta", BETA_DEFAULT)),
            key="beta",
            help="Default 0.86 (India working value). Applies to the refined-"
                 "feed branch into MFG; battery parts (850790) bypass β.",
        )
        st.number_input(
            "γ — total collection rate",
            min_value=0.30, max_value=1.00, step=0.01,
            value=float(st.session_state.get("gamma", GAMMA_TOTAL)),
            key="gamma",
            help="Default 0.98 (Dalberg/USAID). Total collection (formal + "
                 "informal); the split happens downstream at breaking.",
        )

        st.divider()
        st.markdown("**Efficiencies (η)**")
        st.caption("Formal η = literature defaults; informal η = working "
                   "placeholders. δ is shared between lanes.")
        st.number_input("δ — Pb at end-of-life (shared)",
                        0.50, 1.00, ETA_DEFAULTS["delta"], 0.01, key="delta")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("*Formal lane*")
            st.number_input("η_break_F",  0.50, 1.00, ETA_DEFAULTS["eta_break_F"],  0.01, key="eta_break_F")
            st.number_input("η_smelt_F",  0.50, 1.00, ETA_DEFAULTS["eta_smelt_F"],  0.01, key="eta_smelt_F")
            st.number_input("η_refine_F", 0.80, 1.00, ETA_DEFAULTS["eta_refine_F"], 0.01, key="eta_refine_F")
            st.number_input("η_mfg_F",    0.80, 1.00, ETA_DEFAULTS["eta_mfg_F"],    0.01, key="eta_mfg_F")
        with c2:
            st.markdown("*Informal lane*")
            st.number_input("η_break_I",  0.30, 1.00, ETA_DEFAULTS["eta_break_I"],  0.01, key="eta_break_I")
            st.number_input("η_smelt_I",  0.30, 1.00, ETA_DEFAULTS["eta_smelt_I"],  0.01, key="eta_smelt_I")
            st.number_input("η_refine_I", 0.50, 1.00, ETA_DEFAULTS["eta_refine_I"], 0.01, key="eta_refine_I",
                            help="Capped below formal 0.99 by design. Default 0.95.")
            st.number_input("η_mfg_I",    0.50, 1.00, ETA_DEFAULTS["eta_mfg_I"],    0.01, key="eta_mfg_I",
                            help="Capped below formal 0.98 by design. Default 0.95.")
