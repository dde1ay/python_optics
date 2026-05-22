from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SurfaceLayout:
    obj: int = 0
    f1_front: int = 1
    f1_back: int = 2
    stop: int = 3
    f2_front: int = 4
    f2_back: int = 5
    image: int = 6


def get_surface(system: Any, surface_number: int) -> Any:
    return system.LDE.GetSurfaceAt(surface_number)


def set_solve(cell: Any, zosapi: Any, solve_name: str) -> Any:
    solve_type = getattr(zosapi.Editors.SolveType, solve_name)
    solve_data = cell.CreateSolveType(solve_type)
    cell.SetSolveData(solve_data)
    return solve_data


def set_cell_fixed(cell: Any, zosapi: Any) -> Any:
    return set_solve(cell, zosapi, "Fixed")


def set_radius_variable(surface: Any) -> None:
    if not hasattr(surface, "RadiusCell"):
        raise RuntimeError(f"Surface {surface.SurfaceNumber} does not expose RadiusCell.")
    surface.RadiusCell.MakeSolveVariable()


def set_thickness_variable(surface: Any) -> None:
    if not hasattr(surface, "ThicknessCell"):
        raise RuntimeError(f"Surface {surface.SurfaceNumber} does not expose ThicknessCell.")
    surface.ThicknessCell.MakeSolveVariable()


def set_thickness_marginal_ray_height(surface: Any, zosapi: Any) -> Any:
    if not hasattr(surface, "ThicknessCell"):
        raise RuntimeError(f"Surface {surface.SurfaceNumber} does not expose ThicknessCell.")
    return set_solve(surface.ThicknessCell, zosapi, "MarginalRayHeight")


def _solve_settings(solve_data: Any, primary_name: str, aliases: tuple[str, ...]) -> Any:
    for name in (primary_name, *aliases):
        if hasattr(solve_data, name):
            return getattr(solve_data, name)
    available = [name for name in dir(solve_data) if "Pickup" in name or name.startswith("_S_")]
    raise RuntimeError(f"Cannot find {primary_name} solve settings. Available: {available}")


def _set_first_existing(settings: Any, names: tuple[str, ...], value: Any) -> str | None:
    for name in names:
        if hasattr(settings, name):
            setattr(settings, name, value)
            return name
    return None


def set_surface_pickup(cell: Any, zosapi: Any, pickup_surface: int, scale: float = 1.0, offset: float = 0.0, column: Any = None) -> Any:
    solve_data = cell.CreateSolveType(zosapi.Editors.SolveType.SurfacePickup)
    pickup = _solve_settings(
        solve_data,
        "_S_SurfacePickup",
        ("S_SurfacePickup", "_S_SurfacePickup_", "S_SurfacePickup_", "_S_Pickup", "S_Pickup"),
    )
    if _set_first_existing(pickup, ("Surface",), int(pickup_surface)) is None:
        raise RuntimeError("SurfacePickup solve data does not expose Surface.")
    _set_first_existing(pickup, ("ScaleFactor", "Scale"), float(scale))
    _set_first_existing(pickup, ("Offset",), float(offset))
    if column is not None:
        _set_first_existing(pickup, ("Column", "ColumnNumber"), column)
    cell.SetSolveData(solve_data)
    return solve_data


def apply_symmetric_pickups(system: Any, zosapi: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    f1_front = get_surface(system, layout.f1_front)
    f1_back = get_surface(system, layout.f1_back)
    stop = get_surface(system, layout.stop)
    f2_front = get_surface(system, layout.f2_front)
    f2_back = get_surface(system, layout.f2_back)
    set_surface_pickup(stop.ThicknessCell, zosapi, f1_back.SurfaceNumber, scale=1.0)
    set_surface_pickup(f2_front.RadiusCell, zosapi, f1_back.SurfaceNumber, scale=-1.0)
    set_surface_pickup(f2_front.ThicknessCell, zosapi, f1_front.SurfaceNumber, scale=1.0)
    set_surface_pickup(f2_back.RadiusCell, zosapi, f1_front.SurfaceNumber, scale=-1.0)


def release_rear_curvature_pickups(system: Any, zosapi: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    for surface_number in (layout.f2_front, layout.f2_back):
        set_cell_fixed(get_surface(system, surface_number).RadiusCell, zosapi)


def release_stop_airspace_pickup(system: Any, zosapi: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    set_cell_fixed(get_surface(system, layout.stop).ThicknessCell, zosapi)


def set_controlled_stage_solves_fixed(system: Any, zosapi: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    set_cell_fixed(get_surface(system, layout.obj).ThicknessCell, zosapi)
    set_cell_fixed(get_surface(system, layout.f1_front).RadiusCell, zosapi)
    set_cell_fixed(get_surface(system, layout.f1_back).RadiusCell, zosapi)
    set_cell_fixed(get_surface(system, layout.f1_back).ThicknessCell, zosapi)
    set_thickness_marginal_ray_height(get_surface(system, layout.f2_back), zosapi)


def set_airspace_variable(system: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    set_thickness_variable(get_surface(system, layout.f1_back))


def set_front_curvatures_variable(system: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    set_radius_variable(get_surface(system, layout.f1_front))
    set_radius_variable(get_surface(system, layout.f1_back))


def set_all_curvatures_variable(system: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    for surface_number in (layout.f1_front, layout.f1_back, layout.f2_front, layout.f2_back):
        set_radius_variable(get_surface(system, surface_number))


def set_all_airspaces_variable(system: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    for surface_number in (layout.obj, layout.f1_back, layout.stop):
        set_thickness_variable(get_surface(system, surface_number))


def set_object_distance_variable(system: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    set_thickness_variable(get_surface(system, layout.obj))
