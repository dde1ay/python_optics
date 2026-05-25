"""Backward-compatible import surface for merit-function sampling utilities.

The maintained implementation lives in ``periscopic.merit_function_utils``.
This root-level module re-exports the public helpers for older scripts.
"""

from periscopic.merit_function_utils import (
    add_ring_arm_trcx_trcy_operands,
    generate_ring_arm_pupil_points,
    generate_ring_radii,
    get_normalized_field_coordinates,
    validate_zemax_symmetric_3x6_sampling,
)

__all__ = [
    "add_ring_arm_trcx_trcy_operands",
    "generate_ring_arm_pupil_points",
    "generate_ring_radii",
    "get_normalized_field_coordinates",
    "validate_zemax_symmetric_3x6_sampling",
]
