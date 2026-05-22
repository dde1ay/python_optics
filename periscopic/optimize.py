from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import PeriscopicConfig


@dataclass
class OptimizationResult:
    stage_name: str
    merit_value: float | None
    saved_path: str


def _first_existing_attr(obj: Any, names: tuple[str, ...]) -> Any | None:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def calculate_merit(system: Any) -> float | None:
    try:
        return float(system.MFE.CalculateMeritFunction())
    except Exception:
        return None


def run_local_optimization(system: Any, zosapi: Any, config: PeriscopicConfig) -> float | None:
    try:
        tool = system.Tools.OpenLocalOptimization()
    except Exception as exc:
        raise RuntimeError(f"Failed to open Local Optimization tool: {exc}") from exc

    try:
        try:
            algorithm_enum = _first_existing_attr(
                zosapi.Tools.Optimization.OptimizationAlgorithm,
                (config.local_optimization_algorithm, "DampedLeastSquares", "OrthogonalDescent"),
            )
            if algorithm_enum is not None and hasattr(tool, "Algorithm"):
                tool.Algorithm = algorithm_enum
        except Exception:
            pass

        if config.number_of_cores is not None and hasattr(tool, "NumberOfCores"):
            tool.NumberOfCores = int(config.number_of_cores)

        if hasattr(tool, "Cycles"):
            try:
                tool.Cycles = int(config.local_optimization_cycles)
            except Exception:
                pass

        if hasattr(tool, "RunAndWaitForCompletion"):
            tool.RunAndWaitForCompletion()
        elif hasattr(tool, "Run"):
            tool.Run()
        else:
            raise RuntimeError("Local Optimization tool exposes neither RunAndWaitForCompletion nor Run.")
    except Exception as exc:
        raise RuntimeError(f"Local Optimization failed: {exc}") from exc
    finally:
        try:
            tool.Close()
        except Exception:
            pass

    return calculate_merit(system)


def save_system(system: Any, path: Path) -> str:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        system.SaveAs(str(path))
    except Exception as exc:
        raise RuntimeError(f"Failed to save Zemax file to {path}: {exc}") from exc
    return str(path)


def optimize_and_save(system: Any, zosapi: Any, config: PeriscopicConfig, stage_name: str, stage_code: str, optimize: bool = True) -> OptimizationResult:
    merit_value = run_local_optimization(system, zosapi, config) if optimize else calculate_merit(system)
    saved_path = save_system(system, config.stage_path(stage_code))
    return OptimizationResult(stage_name=stage_name, merit_value=merit_value, saved_path=saved_path)
