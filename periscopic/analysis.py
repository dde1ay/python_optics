from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .config import PeriscopicConfig
from .merit import monitor_operand_values, operand_cell


@dataclass
class AnalysisSummary:
    rms_spot_by_field: dict[str, float | None]
    monitor_operands: dict[str, float | None]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _append_temp_operand(mfe: Any, zosapi: Any, operand_name: str) -> Any:
    operand = mfe.AddOperand()
    operand.ChangeType(getattr(zosapi.Editors.MFE.MeritOperandType, operand_name))
    operand.Target = 0.0
    operand.Weight = 0.0
    return operand


def rms_spot_size_by_field(system: Any, zosapi: Any, config: PeriscopicConfig) -> tuple[dict[str, float | None], list[str]]:
    warnings: list[str] = []
    values: dict[str, float | None] = {str(field): None for field in config.field_angles_deg}
    mfe = system.MFE
    start_count = int(mfe.NumberOfOperands)
    try:
        for field_index, field_angle in enumerate(config.field_angles_deg, start=1):
            operand = _append_temp_operand(mfe, zosapi, "RSCE")
            for column_name, value in (("Param1", 0), ("Param2", 1), ("Param3", field_index)):
                try:
                    operand_cell(operand, zosapi, column_name).IntegerValue = int(value)
                except Exception:
                    pass
            try:
                mfe.CalculateMeritFunction()
                values[str(field_angle)] = float(operand.Value)
            except Exception as exc:
                warnings.append(f"Could not evaluate RSCE for field {field_angle}: {exc}")
    except Exception as exc:
        warnings.append(f"RMS spot size extraction unavailable: {exc}")
    finally:
        try:
            extra_count = int(mfe.NumberOfOperands) - start_count
            if extra_count > 0:
                mfe.RemoveOperandsAt(start_count + 1, extra_count)
        except Exception as exc:
            warnings.append(f"Could not restore MFE after temporary RSCE operands: {exc}")
    return values, warnings


def run_analysis_window(system: Any, zosapi: Any, analysis_name: str, enum_candidates: tuple[str, ...]) -> str | None:
    enum_value = None
    for candidate in enum_candidates:
        if hasattr(zosapi.Analysis.AnalysisIDM, candidate):
            enum_value = getattr(zosapi.Analysis.AnalysisIDM, candidate)
            break
    if enum_value is None:
        return f"Analysis enum not found for {analysis_name}: {enum_candidates}"
    analysis = None
    try:
        analysis = system.Analyses.New_Analysis_SettingsFirst(enum_value)
        analysis.ApplyAndWaitForCompletion()
        return None
    except Exception as exc:
        return f"{analysis_name} analysis failed: {exc}"
    finally:
        try:
            if analysis is not None:
                analysis.Close()
        except Exception:
            pass


def analyze_system(system: Any, zosapi: Any, config: PeriscopicConfig) -> AnalysisSummary:
    warnings: list[str] = []
    rms, rms_warnings = rms_spot_size_by_field(system, zosapi, config)
    warnings.extend(rms_warnings)
    monitors = monitor_operand_values(system)
    for analysis_name, enums in (
        ("Ray Fan", ("RayFan",)),
        ("Field Curvature", ("FieldCurvatureAndDistortion",)),
        ("Seidel", ("SeidelDiagram", "SeidelCoefficients", "Seidel")),
    ):
        warning = run_analysis_window(system, zosapi, analysis_name, enums)
        if warning:
            warnings.append(warning)
    return AnalysisSummary(rms_spot_by_field=rms, monitor_operands=monitors, warnings=warnings)
