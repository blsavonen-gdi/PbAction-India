"""Session-state defaults + the canonical chain solve.

Everything else in the app reads from `compute_state()`. Editing any input
through the sidebar or Tab 2 controls forces a re-solve on the next rerun.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from india_model.model_v4 import (
    fit_growth_rate, tau_eff,
    FEED_HS, PARTS_HS, CRUDE_HS,
)
from india_model.model_v5_parallel import (
    forward_parallel_chain,
    REF_PHI, PHI_FLOORS, ETA_DEFAULTS,
    BETA_DEFAULT, GAMMA_TOTAL,
)


# ---- file locations -------------------------------------------------------

ROOT = Path(__file__).parent.parent
DATA_CSV     = ROOT / "india_model" / "india_mass_balance_2018_2023.csv"
SEGMENTS_CSV = ROOT / "india_model" / "segment_lifetimes.csv"

# Smoothing window used by the residual / chain inputs (mirrors model_v4).
FIT_WINDOW = (2019, 2022)
SMOOTH_WINDOW = 3


# ---- cached file loaders --------------------------------------------------

@st.cache_data(show_spinner=False)
def load_raw_csv() -> pd.DataFrame:
    return pd.read_csv(DATA_CSV).sort_values("year").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_segments_df() -> pd.DataFrame:
    return pd.read_csv(SEGMENTS_CSV)


# ---- arr builder ----------------------------------------------------------

def build_arr_from_user_inputs(df_csv: pd.DataFrame,
                               user_stock: pd.DataFrame,
                               fit_window: tuple[int, int] = FIT_WINDOW
                               ) -> dict:
    """Replicate v4 load_inputs(smooth_window=3, trim_years=...) using the
    user's edited stock table. Returns the `arr` dict the parallel chain
    consumes.
    """
    df = df_csv.copy().sort_values("year").reset_index(drop=True)
    user_stock = user_stock.copy()
    user_stock["year"] = user_stock["year"].astype(int)
    stock_lookup = dict(zip(user_stock["year"].tolist(),
                            user_stock["stock_total_t_pb"].astype(float).tolist()))
    df["stock_total_t_pb"] = df["year"].astype(int).map(
        lambda y: stock_lookup.get(int(y), df.loc[df["year"] == y, "stock_total_t_pb"].iloc[0])
    )

    # 3-yr centered rolling smoothing on every numeric column
    numeric = [c for c in df.columns if c != "year"]
    rolled = df[numeric].rolling(window=SMOOTH_WINDOW, center=True,
                                 min_periods=SMOOTH_WINDOW).mean()
    df_s = pd.concat([df["year"], rolled], axis=1)
    trim_years = list(range(fit_window[0], fit_window[1] + 1))
    first_year = min(trim_years)
    pre_year = first_year - 1
    stock_pre = float(df.loc[df["year"] == pre_year, "stock_total_t_pb"].iloc[0])
    df_s = df_s[df_s["year"].isin(trim_years)].reset_index(drop=True)

    feed_imp_cols = [f"imp_{hs}_t_pb" for hs in FEED_HS]
    feed_exp_cols = [f"exp_{hs}_t_pb" for hs in FEED_HS]
    arr = {
        "year":       df_s["year"].to_numpy(dtype=int),
        "stock":      df_s["stock_total_t_pb"].to_numpy(dtype=float),
        "stock_pre":  stock_pre,
        "mine_usgs":  df_s["mine_pb_t_usgs"].to_numpy(dtype=float),
        "prim_usgs":  df_s["primary_pb_t_usgs"].to_numpy(dtype=float),
        "sec_usgs":   df_s["secondary_pb_t_usgs"].to_numpy(dtype=float),
        "imp_ore":    df_s["imp_260700_t_pb"].to_numpy(dtype=float),
        "exp_ore":    df_s["exp_260700_t_pb"].to_numpy(dtype=float),
        "imp_feed":   df_s[feed_imp_cols].sum(axis=1).to_numpy(dtype=float),
        "exp_feed":   df_s[feed_exp_cols].sum(axis=1).to_numpy(dtype=float),
        "imp_parts":  df_s[f"imp_{PARTS_HS}_t_pb"].to_numpy(dtype=float),
        "exp_parts":  df_s[f"exp_{PARTS_HS}_t_pb"].to_numpy(dtype=float),
        "imp_crude":  df_s[f"imp_{CRUDE_HS}_t_pb"].to_numpy(dtype=float),
        "exp_crude":  df_s[f"exp_{CRUDE_HS}_t_pb"].to_numpy(dtype=float),
        "imp_batt":   (df_s["imp_850710_t_pb"] + df_s["imp_850720_t_pb"]).to_numpy(dtype=float),
        "exp_batt":   (df_s["exp_850710_t_pb"] + df_s["exp_850720_t_pb"]).to_numpy(dtype=float),
        "imp_used":   df_s["imp_854810_t_pb"].to_numpy(dtype=float),
        "exp_used":   df_s["exp_854810_t_pb"].to_numpy(dtype=float),
        "imp_scrap":  df_s["imp_780200_t_pb"].to_numpy(dtype=float),
        "exp_scrap":  df_s["exp_780200_t_pb"].to_numpy(dtype=float),
    }
    return arr


# ---- canonical chain solve ------------------------------------------------

def compute_state() -> dict:
    """Pull every input from st.session_state, run the chain, return a dict.

    Inputs are populated by app.sidebar (eta + beta + gamma) and app.controls
    (stock, segments, k, tau-override, phi). This function is the only place
    the chain is called for the dashboard.
    """
    df_csv = load_raw_csv()

    # Stock (edited table or default)
    user_stock = st.session_state.get("user_stock")
    if user_stock is None:
        user_stock = df_csv[["year", "stock_total_t_pb"]].copy()

    # Segments (edited table or default)
    user_segments = st.session_state.get("user_segments")
    if user_segments is None:
        user_segments = load_segments_df()

    arr = build_arr_from_user_inputs(df_csv, user_stock, FIT_WINDOW)
    g_val   = float(fit_growth_rate(user_stock["stock_total_t_pb"].to_numpy(dtype=float),
                                    user_stock["year"].to_numpy(dtype=float)))
    tau_seg = float(tau_eff(user_segments))
    tau_override = bool(st.session_state.get("tau_override", False))
    tau_main = float(st.session_state.get("tau_slider", tau_seg)) if tau_override else tau_seg

    beta  = float(st.session_state.get("beta",  BETA_DEFAULT))
    gamma = float(st.session_state.get("gamma", GAMMA_TOTAL))
    k     = float(st.session_state.get("k_stock", 1.0))

    phi = {
        "phi_break_f":  float(st.session_state.get("phi_break_f",  REF_PHI["phi_break_f"])),
        "phi_smelt_f":  float(st.session_state.get("phi_smelt_f",  REF_PHI["phi_smelt_f"])),
        "phi_refine_f": float(st.session_state.get("phi_refine_f", REF_PHI["phi_refine_f"])),
        "phi_mfg_f":    float(st.session_state.get("phi_mfg_f",    REF_PHI["phi_mfg_f"])),
    }
    etas = {key: float(st.session_state.get(key, default))
            for key, default in ETA_DEFAULTS.items()}

    out = forward_parallel_chain(
        arr, k_stock=k, phi=phi,
        beta=beta, gamma=gamma, g=g_val, tau=tau_main,
        **etas,
    )

    return {
        "arr":           arr,
        "user_stock":    user_stock,
        "user_segments": user_segments,
        "g":             g_val,
        "tau_seg":       tau_seg,
        "tau_main":      tau_main,
        "tau_override":  tau_override,
        "beta":          beta,
        "gamma":         gamma,
        "k":             k,
        "phi":           phi,
        "etas":          etas,
        "chain":         out,
    }
