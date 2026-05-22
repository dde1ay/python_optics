from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import PeriscopicConfig
from .merit_function_utils import add_ring_arm_trcx_trcy_operands


MONITOR_OPERANDS = ("EFLY", "SPHA", "COMA", "ASTI", "PETC", "DIST")


@dataclass
class MeritOperandRecord:
    row: int
    operand_type: str
    target: float
    weight: float


def clear_merit_function(mfe: Any) -> None:
    count = int(mfe.NumberOfOperands)
    if count > 0:
        mfe.RemoveOperandsAt(1, count)


def add_operand(mfe: Any, zosapi: Any, operand_name: str, target: float = 0.0, weight: float = 0.0) -> Any:
    if not hasattr(zosapi.Editors.MFE.MeritOperandType, operand_name):
        raise RuntimeError(f"Merit operand {operand_name} is not available in this ZOS-API version.")
    operand = mfe.AddOperand()
    operand.ChangeType(getattr(zosapi.Editors.MFE.MeritOperandType, operand_name))
    operand.Target = target
    operand.Weight = weight
    return operand


def operand_cell(operand: Any, zosapi: Any, column_name: str) -> Any:
    column = getattr(zosapi.Editors.MFE.MeritColumn, column_name)
    return operand.GetOperandCell(column)


def set_operand_surface_range_with_api(operand: Any, zosapi: Any, start_surface: int = 1, end_surface: int = 2) -> None:
    try:
        operand_cell(operand, zosapi, "Param1").IntegerValue = int(start_surface)
        operand_cell(operand, zosapi, "Param2").IntegerValue = int(end_surface)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to set operand surface range to {start_surface}-{end_surface}: {exc}"
        ) from exc


def add_focal_length_control(
    mfe: Any,
    zosapi: Any,
    config: PeriscopicConfig,
    weight: float,
    start_surface: int = 1,
    end_surface: int = 2,
) -> Any:
    operand = add_operand(mfe, zosapi, "EFFL", config.effective_focal_length, weight)
    set_operand_surface_range_with_api(operand, zosapi, start_surface, end_surface)
    return operand


def add_efly_monitor(
    mfe: Any,
    zosapi: Any,
    config: PeriscopicConfig,
    start_surface: int = 1,
    end_surface: int = 2,
) -> Any:
    operand = add_operand(mfe, zosapi, "EFLY", config.effective_focal_length, 0.0)
    set_operand_surface_range_with_api(operand, zosapi, start_surface, end_surface)
    return operand


def build_initial_merit(
    system: Any,
    zosapi: Any,
    config: PeriscopicConfig,
    pmag_weight: float | None = None,
    effl_weight: float = 0.0,
) -> None:
    mfe = system.MFE
    clear_merit_function(mfe)
    add_focal_length_control(mfe, zosapi, config, effl_weight)
    add_efly_monitor(mfe, zosapi, config)
    add_operand(mfe, zosapi, "PMAG", config.pmag_target, config.pmag_weight if pmag_weight is None else pmag_weight)
    for operand_name in MONITOR_OPERANDS:
        if operand_name == "EFLY":
            continue
        add_operand(mfe, zosapi, operand_name, 0.0, 0.0)


def add_stage0_default_trcx_trcy(system: Any) -> dict[str, Any]:
    return add_ring_arm_trcx_trcy_operands(
        system,
        rings=3,
        arms=6,
        radius_mode="gaussian",
        clear_existing=False,
        target=0.0,
        wavelength=1,
        comment_prefix=True,
    )


def build_infinity_merit(system: Any, zosapi: Any, config: PeriscopicConfig, include_trac: bool = True) -> None:
    mfe = system.MFE
    clear_merit_function(mfe)
    add_focal_length_control(mfe, zosapi, config, config.efly_weight)
    add_efly_monitor(mfe, zosapi, config)
    add_operand(mfe, zosapi, "PMAG", config.pmag_target, 0.0)
    if include_trac:
        add_default_spot_rms_trcx_trcy(system, zosapi, config)
    for operand_name in MONITOR_OPERANDS:
        if operand_name == "EFLY":
            continue
        add_operand(mfe, zosapi, operand_name, 0.0, 0.0)


def add_default_spot_rms_trcx_trcy(system: Any, zosapi: Any, config: PeriscopicConfig) -> None:
    add_ring_arm_trcx_trcy_operands(
        system,
        rings=3,
        arms=6,
        radius_mode="gaussian",
        clear_existing=False,
        target=0.0,
        wavelength=1,
        comment_prefix=True,
    )


def _add_field_curvature_operand(system: Any, zosapi: Any, operand_name: str, field_index: int) -> None:
    operand = add_operand(system.MFE, zosapi, operand_name, 0.0, 1.0)
    try:
        operand_cell(operand, zosapi, "Param1").IntegerValue = int(field_index)
    except Exception:
        pass


def add_tangential_field_flattening(system: Any, zosapi: Any, config: PeriscopicConfig) -> None:
    for field_index, _field in enumerate(config.field_angles_deg, start=1):
        _add_field_curvature_operand(system, zosapi, "FCGT", field_index)


def add_sagittal_field_flattening(system: Any, zosapi: Any, config: PeriscopicConfig) -> None:
    for field_index, _field in enumerate(config.field_angles_deg, start=1):
        _add_field_curvature_operand(system, zosapi, "FCGS", field_index)


def monitor_operand_values(system: Any) -> dict[str, float | None]:
    values: dict[str, float | None] = {name: None for name in MONITOR_OPERANDS}
    mfe = system.MFE
    try:
        mfe.CalculateMeritFunction()
    except Exception:
        return values
    for row in range(1, int(mfe.NumberOfOperands) + 1):
        operand = mfe.GetOperandAt(row)
        operand_name = str(operand.Type).split(".")[-1]
        if operand_name in values:
            try:
                values[operand_name] = float(operand.Value)
            except Exception:
                values[operand_name] = None
    return values
