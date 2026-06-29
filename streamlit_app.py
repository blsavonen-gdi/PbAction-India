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
    page_title="Lead Material Flow Analysis v5 (India)",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import after set_page_config to keep streamlit happy
from app import sidebar, controls, diagram, diagnostics, readme  # noqa: E402


def main() -> None:
    st.title("Lead Material Flow Analysis v5 (India)")
    st.markdown(
        "A material flow analysis of lead through India's battery cycle — "
        "from retirement and collection through breaking, smelting, refining, "
        "and manufacturing to installed stock. The chain is anchored to USGS "
        "primary/secondary production and UN Comtrade customs flows, and "
        "responds in real time to edits in the sidebar and Tab 2."
    )
    st.markdown("**What is unique about this version**")
    st.markdown(
        "- Parallel formal/informal lanes through break, smelt, refine, and manufacture.\n"
        "- USGS secondary is a one-sided floor on formal refined output.\n"
        "- Tab 2 carries stock / segments / k / τ / φ; the sidebar carries the process parameters (β, γ, η).\n"
        "- Tab 4 carries the original toolkit's diagnostics."
    )

    sidebar.render()

    tab1, tab2, tab3, tab4 = st.tabs([
        "1. Flow diagram",
        "2. Controls",
        "3. README",
        "4. Diagnostics",
    ])
    with tab1:
        diagram.render()
    with tab2:
        controls.render()
    with tab3:
        readme.render()
    with tab4:
        diagnostics.render()


if __name__ == "__main__":
    main()
