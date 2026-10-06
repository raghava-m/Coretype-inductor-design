"""Three-phase inductor analytical design (vendored from Transformer-design-app)."""

from .analytical_design import (
    ThreePhaseCornerData,
    ThreePhaseDesignInputs,
    ThreePhaseElectricalInputs,
    ThreePhaseInsulationCoordination,
    ThreePhaseStripData,
    ThreePhaseVariableCalculations,
    ThreePhaseVariableInputs,
    run_three_phase_design,
)
from .material_library import conductor_names, core_names, core_properties
from .schema import DEFAULT_SPEC, compact_row, spec_from_dict, summarize_design
from .three_phase_engine import ThreePhaseInput, calculate_three_phase_inductor
from .tradeoff import run_tradeoff

__all__ = [
    "ThreePhaseDesignInputs",
    "ThreePhaseElectricalInputs",
    "ThreePhaseVariableInputs",
    "ThreePhaseInsulationCoordination",
    "ThreePhaseVariableCalculations",
    "ThreePhaseStripData",
    "ThreePhaseCornerData",
    "run_three_phase_design",
    "calculate_three_phase_inductor",
    "ThreePhaseInput",
    "spec_from_dict",
    "summarize_design",
    "compact_row",
    "DEFAULT_SPEC",
    "run_tradeoff",
    "conductor_names",
    "core_names",
    "core_properties",
]
