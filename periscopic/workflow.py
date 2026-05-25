from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .analysis import analyze_system
from .config import PeriscopicConfig
from .lens_builder import build_initial_system, ensure_dummy_image_surface, set_object_at_infinity
from .merit import build_infinity_merit, build_initial_merit
from .optimize import OptimizationResult, optimize_and_save
from .solves import (
    SurfaceLayout,
    apply_symmetric_pickups,
    set_airspace_variable,
    set_cell_fixed,
    set_controlled_stage_solves_fixed,
    set_front_curvatures_variable,
    set_object_distance_variable,
    set_radius_variable,
    set_thickness_marginal_ray_height,
    set_thickness_variable,
)


def _stage_record(stage_name: str, result: OptimizationResult, analysis: Any) -> dict[str, Any]:
    return {
        "stage_name": stage_name,
        "merit_value": result.merit_value,
        "saved_path": result.saved_path,
        "analysis": analysis.to_dict(),
    }


def _print_stage(record: dict[str, Any]) -> None:
    print(f"\n[{record['stage_name']}]")
    print(f"  merit: {record['merit_value']}")
    print(f"  saved: {record['saved_path']}")
    print(f"  RMS spot by field: {record['analysis']['rms_spot_by_field']}")
    print(f"  monitors: {record['analysis']['monitor_operands']}")
    for warning in record["analysis"].get("warnings", []):
        print(f"  warning: {warning}")


def _analyze_and_record(system: Any, zosapi: Any, config: PeriscopicConfig, result: OptimizationResult) -> dict[str, Any]:
    analysis = analyze_system(system, zosapi, config)
    record = _stage_record(result.stage_name, result, analysis)
    _print_stage(record)
    return record


def _write_summary(config: PeriscopicConfig, records: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {"config": _jsonable_config(config), "stages": records}
    summary_path = config.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary written to {summary_path}")
    return summary


def _after_stage(config: PeriscopicConfig, records: list[dict[str, Any]], stage_index: int) -> bool:
    if config.stop_after_stage is not None and stage_index >= config.stop_after_stage:
        _write_summary(config, records)
        print(f"Stopped after Stage {stage_index}.")
        return True
    if config.pause_after_stage:
        input(f"\nStage {stage_index} complete. Press Enter to continue to the next stage...")
    return False


def _should_run_stage(config: PeriscopicConfig, stage_index: int) -> bool:
    return config.only_stage is None or stage_index >= config.only_stage


def _set_all_pickups_variable(system: Any, layout: SurfaceLayout) -> None:
    lde = system.LDE
    set_thickness_variable(lde.GetSurfaceAt(layout.stop))
    set_radius_variable(lde.GetSurfaceAt(layout.f2_front))
    set_radius_variable(lde.GetSurfaceAt(layout.f2_back))


def run_workflow(system: Any, zosapi: Any, config: PeriscopicConfig) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    layout = SurfaceLayout()
    records: list[dict[str, Any]] = []

    if _should_run_stage(config, 0):
        print("\nStage 0: build_initial_system")
        build_initial_system(system, zosapi, config)
        build_initial_merit(system, zosapi, config, pmag_weight=0.0, effl_weight=0.0)
        result = optimize_and_save(system, zosapi, config, "Stage 0: build_initial_system", "PERC100a", optimize=False)
        records.append(_analyze_and_record(system, zosapi, config, result))
        if _after_stage(config, records, 0):
            return {"config": _jsonable_config(config), "stages": records}

    if _should_run_stage(config, 1):
        print("\nStage 1: recover_target_efl")
        set_controlled_stage_solves_fixed(system, zosapi, layout)
        set_airspace_variable(system, layout)
        build_initial_merit(system, zosapi, config, pmag_weight=0.0, effl_weight=1.0)
        result = optimize_and_save(system, zosapi, config, "Stage 1: recover_target_efl", "PERC101a")
        records.append(_analyze_and_record(system, zosapi, config, result))
        if _after_stage(config, records, 1):
            return {"config": _jsonable_config(config), "stages": records}

    if _should_run_stage(config, 2):
        print("\nStage 2: unit_magnification")
        set_cell_fixed(system.LDE.GetSurfaceAt(layout.f1_back).ThicknessCell, zosapi)
        build_initial_merit(system, zosapi, config, pmag_weight=1.0, effl_weight=1.0)
        set_object_distance_variable(system, layout)
        result = optimize_and_save(system, zosapi, config, "Stage 2: unit_magnification", "PERC102a")
        records.append(_analyze_and_record(system, zosapi, config, result))
        if _after_stage(config, records, 2):
            return {"config": _jsonable_config(config), "stages": records}

    if _should_run_stage(config, 3):
        print("\nStage 3: object_at_infinity")
        set_object_at_infinity(system, zosapi, layout)
        build_infinity_merit(system, zosapi, config, include_trac=True)
        set_cell_fixed(system.LDE.GetSurfaceAt(layout.obj).ThicknessCell, zosapi)
        set_airspace_variable(system, layout)
        apply_symmetric_pickups(system, zosapi, layout)
        set_thickness_marginal_ray_height(system.LDE.GetSurfaceAt(layout.f2_back), zosapi)
        set_front_curvatures_variable(system, layout)
        result = optimize_and_save(system, zosapi, config, "Stage 3: object_at_infinity", "PERC103a")
        records.append(_analyze_and_record(system, zosapi, config, result))
        if _after_stage(config, records, 3):
            return {"config": _jsonable_config(config), "stages": records}

    if _should_run_stage(config, 4):
        print("\nStage 4: thickness_and_dummy_surface")
        dummy_surface = ensure_dummy_image_surface(system, layout)
        system.LDE.GetSurfaceAt(layout.f1_front).Thickness = config.final_thickness
        dummy = system.LDE.GetSurfaceAt(dummy_surface)
        dummy.Thickness = 0.0
        set_thickness_variable(dummy)
        result = optimize_and_save(system, zosapi, config, "Stage 4: thickness_and_dummy_surface", "PERC104a")
        records.append(_analyze_and_record(system, zosapi, config, result))
        if _after_stage(config, records, 4):
            return {"config": _jsonable_config(config), "stages": records}

    if _should_run_stage(config, 5):
        print("\nStage 5: release_pickups")
        _set_all_pickups_variable(system, layout)
        result = optimize_and_save(system, zosapi, config, "Stage 5: release_pickups", "PERC105a")
        records.append(_analyze_and_record(system, zosapi, config, result))
        if _after_stage(config, records, 5):
            return {"config": _jsonable_config(config), "stages": records}

    return _write_summary(config, records)


def _jsonable_config(config: PeriscopicConfig) -> dict[str, Any]:
    data = asdict(config)
    data["output_dir"] = str(config.output_dir)
    return data
