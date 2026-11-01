"""Optional, read-only explanation from the state-adaptive kernel bank."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from tp.kernels import analyze_kernels


def render() -> None:
    session = st.session_state
    chip = session.get("area_chip")
    meta = session.get("area_meta") or {}
    current = session.get("kernel_explanation")
    if current is not None:
        previous_chip = current.get("source_chip")
        if chip is None or previous_chip is None or not np.array_equal(chip, previous_chip):
            current = None
            session["kernel_explanation"] = None

    with st.expander("Explainable kernel analysis", expanded=current is not None):
        st.caption(
            "Optional filter evidence for the current processed chip. "
            "This analysis does not alter the model result or trust verdict."
        )
        if chip is None:
            st.info("Process an area first to run the kernel explanation on its real chip.")
            return

        if st.button("Run kernel explanation", key="kernel_explanation_run"):
            try:
                report = analyze_kernels(chip, int(meta.get("offset", 1000)))
                current = {"source_chip": np.asarray(chip).copy(), "report": report}
                session["kernel_explanation"] = current
            except (TypeError, ValueError) as exc:
                st.error(f"Kernel analysis could not use this chip ({type(exc).__name__}).")
                return

        if current is None:
            st.caption("Choose Run kernel explanation to calculate the filter maps.")
            return

        report = current["report"]
        columns = st.columns(3)
        columns[0].metric("Image state", report["state"].title())
        columns[1].metric("Kernel anomaly score", f"{report['score']:.3f}")
        columns[2].metric("Active filters", str(len(report["kernels"])))
        st.caption("Filters used: " + ", ".join(report["kernels"]))
        st.image(
            report["anomaly_map"],
            caption="Kernel anomaly map · relative filter evidence, not a verdict",
            clamp=True,
            use_container_width=True,
        )
        if report.get("scores"):
            st.dataframe(
                pd.DataFrame(
                    [{"Filter": name, "Relative score": score} for name, score in report["scores"].items()]
                ),
                hide_index=True,
                width="stretch",
            )
