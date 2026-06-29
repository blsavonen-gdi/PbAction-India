"""Tab 3 — readme renderer.

Pulls README.md from the repo root and renders it. The user can drop their
doc into README.md and the tab will pick it up on the next rerun.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st


ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"


def render() -> None:
    if not README.exists():
        st.info(
            "Tab 3 will render `README.md` from the repo root. The file is "
            "missing — add a `README.md` to the project root and it will "
            "appear here on the next rerun."
        )
        return
    text = README.read_text(encoding="utf-8")
    st.markdown(text)
