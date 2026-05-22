from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import PeriscopicConfig
from .solves import SurfaceLayout, apply_symmetric_pickups, set_front_curvatures_variable, set_object_distance_variable, set_thickness_marginal_ray_height, set_thickness_variable


@dataclass
class BuildResult:
    layout: SurfaceLayout
    field_type_name: str
    aperture_type_name: str
    aperture_value: float
    material_first: str
    material_second: str


def first_existing_attr(obj: Any, names: list[str] | tuple[str, ...]) -> tuple[Any, str] | tuple[None, None]:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name), name
    return None, None


def set_primary_wavelength(system: Any, wavelength_um: float) -> None:
    wavelengths = system.SystemData.Wavelengths
    while int(wavelengths.NumberOfWavelengths) > 1:
        wavelengths.RemoveWavelength(2)
    wave = wavelengths.GetWavelength(1)
    wave.Wavelength = wavelength_um
    wave.Weight = 1.0


def set_angle_fields(system: Any, zosapi: Any, field_angles: tuple[float, ...]) -> str:
    fields = system.SystemData.Fields
    field_type, field_type_name = first_existing_attr(zosapi.SystemData.FieldType, ("Angle", "FieldAngle"))
    if field_type is None:
        raise RuntimeError("Cannot find angle field enum in ZOSAPI.SystemData.FieldType.")
    fields.SetFieldType(field_type)
    while int(fields.NumberOfFields) > 1:
        fields.DeleteField(2)
    first = fields.GetField(1)
    first.X = 0.0
    first.Y = float(field_angles[0])
    first.Weight = 1.0
    for angle in field_angles[1:]:
        fields.AddField(0.0, float(angle), 1.0)
    return field_type_name


def set_aperture_to_paraxial_working_f_number(system: Any, zosapi: Any, f_number: float) -> tuple[str, float]:
    aperture = system.SystemData.Aperture
    aperture_type, aperture_name = first_existing_attr(
        zosapi.SystemData.ZemaxApertureType,
        ("ParaxialWorkingFNum", "ImageSpaceFNum", "EntrancePupilDiameter", "FloatByStopSize"),
    )
    if aperture_type is None:
        raise RuntimeError("Cannot find a supported aperture type enum.")
    aperture.ApertureType = aperture_type
    aperture.ApertureValue = f_number
    return aperture_name, aperture.ApertureValue


def ensure_surface_count(lde: Any, surface_count: int) -> list[Any]:
    while int(lde.NumberOfSurfaces) < surface_count:
        lde.InsertNewSurfaceAt(int(lde.NumberOfSurfaces) - 1)
    while int(lde.NumberOfSurfaces) > surface_count:
        lde.RemoveSurfaceAt(2)
    return [lde.GetSurfaceAt(i) for i in range(surface_count)]


def make_surface_stop(surface: Any) -> None:
    if hasattr(surface, "MakeSurfaceStop"):
        surface.MakeSurfaceStop()
    else:
        surface.IsStop = True


def set_first_available_material(surface: Any, material_names: tuple[str, ...]) -> str:
    last_error: Exception | None = None
    for material_name in material_names:
        try:
            surface.Material = material_name
            return material_name
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Cannot set material from {material_names}: {last_error}")


def clear_system(system: Any) -> None:
    try:
        system.New(False)
    except Exception as exc:
        raise RuntimeError(f"Failed to create a new sequential system: {exc}") from exc


def setup_units(system: Any) -> None:
    # OpticStudio defaults are usually mm. Set when the enum is exposed; otherwise leave default.
    try:
        units = system.SystemData.Units
        if hasattr(units, "LensUnits") and hasattr(units, "Units"):
            pass
    except Exception:
        return


def build_initial_system(system: Any, zosapi: Any, config: PeriscopicConfig) -> BuildResult:
    clear_system(system)
    setup_units(system)
    lde = system.LDE
    layout = SurfaceLayout()
    obj, f1_front, f1_back, stop, f2_front, f2_back, image = ensure_surface_count(lde, 7)

    set_primary_wavelength(system, config.wavelength_um)
    field_type_name = set_angle_fields(system, zosapi, config.field_angles_deg)
    aperture_name, aperture_value = set_aperture_to_paraxial_working_f_number(system, zosapi, config.working_f_number)

    obj.Comment = "Finite object"
    obj.Thickness = config.initial_object_distance

    f1_front.Comment = "First SF2 lens front"
    f1_front.Radius = config.initial_radius
    f1_front.Thickness = config.initial_thickness
    material_first = set_first_available_material(f1_front, config.glass_fallbacks)

    f1_back.Comment = "First SF2 lens back"
    f1_back.Radius = -config.initial_radius
    f1_back.Thickness = config.half_lens_separation

    stop.Comment = "STOP / pickup surface 2 thickness"
    stop.Thickness = config.half_lens_separation
    make_surface_stop(stop)

    f2_front.Comment = "Second SF2 lens front / pickup"
    f2_front.Radius = config.initial_radius
    f2_front.Thickness = config.initial_thickness
    material_second = set_first_available_material(f2_front, config.glass_fallbacks)

    f2_back.Comment = "Second SF2 lens back / pickup"
    f2_back.Radius = -config.initial_radius
    f2_back.Thickness = config.initial_object_distance

    image.Comment = "Unit-magnification image"

    set_front_curvatures_variable(system, layout)
    set_object_distance_variable(system, layout)
    set_thickness_variable(f1_back)
    apply_symmetric_pickups(system, zosapi, layout)
    set_thickness_marginal_ray_height(f2_back, zosapi)
    system.UpdateStatus()
    return BuildResult(layout, field_type_name, aperture_name, aperture_value, material_first, material_second)


def set_object_at_infinity(system: Any, zosapi: Any, layout: SurfaceLayout = SurfaceLayout()) -> None:
    obj = system.LDE.GetSurfaceAt(layout.obj)
    try:
        obj.Thickness = float("inf")
    except Exception:
        obj.Thickness = 1.0e10
    try:
        obj.ThicknessCell.SetSolveData(obj.ThicknessCell.CreateSolveType(zosapi.Editors.SolveType.Fixed))
    except Exception:
        pass


def set_lens_thickness(system: Any, thickness: float, layout: SurfaceLayout = SurfaceLayout()) -> None:
    system.LDE.GetSurfaceAt(layout.f1_front).Thickness = thickness
    system.LDE.GetSurfaceAt(layout.f2_front).Thickness = thickness


def ensure_dummy_image_surface(system: Any, layout: SurfaceLayout = SurfaceLayout()) -> int:
    lde = system.LDE
    image_index = int(lde.NumberOfSurfaces) - 1
    if image_index >= 7:
        return image_index - 1
    lde.InsertNewSurfaceAt(image_index)
    dummy = lde.GetSurfaceAt(image_index)
    dummy.Comment = "Dummy image surface"
    dummy.Thickness = 0.0
    lde.GetSurfaceAt(image_index + 1).Comment = "Final image"
    return image_index
