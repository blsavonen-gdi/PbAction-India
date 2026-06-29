"""India Lead Mass-Balance — Streamlit dashboard (v5 parallel chain).

Three tabs:
  1. Flow diagram — interactive system view with per-node detail + line graph
  2. Controls    — user-editable inputs (stock / segments / k / τ / φ)
  3. README      — project documentation pulled from README.md

Sidebar holds the process parameters (β, γ, all formal + informal η's), so a
change there is reflected in the flow numbers on Tab 1 immediately.
"""

from __future__ import annotations

import streamlit as st

# Page config first so other modules can call st.* freely
st.set_page_config(
    page_title="India Lead Mass-Balance",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import after set_page_config to keep streamlit happy
from app import sidebar, controls, diagram, readme  # noqa: E402


def main() -> None:
    st.title("India Lead Mass-Balance — v5 parallel chain")
    st.caption(
        "Parallel formal/informal lanes through break, smelt, refine, and "
        "manufacture. USGS secondary is a one-sided floor on formal refined "
        "output. Use Tab 2 for stock/segments/k/τ/φ; use the sidebar for "
        "process parameters (β, γ, η)."
    )

    sidebar.render()

    tab1, tab2, tab3 = st.tabs([
        "1. Flow diagram",
        "2. Controls",
        "3. README",
    ])
    with tab1:
        diagram.render()
    with tab2:
        controls.render()
    with tab3:
        readme.render()


if __name__ == "__main__":
    main()
