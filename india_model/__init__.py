"""India lead mass-balance model.

Two modules:

  model_v4 — retirement-engine utilities and the legacy three-stage chain.
             v5 imports retire_rate / tau_eff / fit_growth_rate / load_inputs
             from here. The legacy forward_chain function is unused by the
             dashboard but kept available for reference.

  model_v5_parallel — the parallel formal/informal chain (4 phi, both lanes
                      at every stage, USGS one-sided floor on REFINE_SEC_F).
"""
