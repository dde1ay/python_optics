def first_existing_attr(obj, names):
    """Return the first existing enum/member value from a list of possible API names."""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name), name
    return None, None


def set_primary_wavelength(system, wavelength_um):
    wavelengths = system.SystemData.Wavelengths
    while int(wavelengths.NumberOfWavelengths) > 1:
        wavelengths.RemoveWavelength(2)
    wave = wavelengths.GetWavelength(1)
    wave.Wavelength = wavelength_um
    wave.Weight = 1.0


def set_angle_fields(system, zosapi, field_angles):
    fields = system.SystemData.Fields
    field_type, field_type_name = first_existing_attr(
        zosapi.SystemData.FieldType,
        ['Angle', 'FieldAngle'],
    )
    if field_type is None:
        raise RuntimeError('Cannot find an angle field type enum.')
    fields.SetFieldType(field_type)

    while int(fields.NumberOfFields) > 1:
        fields.DeleteField(2)

    first_field = fields.GetField(1)
    first_field.X = 0.0
    first_field.Y = float(field_angles[0])
    first_field.Weight = 1.0

    for angle in field_angles[1:]:
        fields.AddField(0.0, float(angle), 1.0)
    return field_type_name


def set_aperture_to_paraxial_working_f_number(system, zosapi, f_number):
    """Set the system aperture to paraxial working F/#, with conservative fallbacks."""
    aperture = system.SystemData.Aperture
    aperture_type, aperture_name = first_existing_attr(
        zosapi.SystemData.ZemaxApertureType,
        [
            'ParaxialWorkingFNum',
            'ImageSpaceFNum',
            'EntrancePupilDiameter',
            'FloatByStopSize',
        ],
    )
    if aperture_type is None:
        raise RuntimeError('Cannot find a supported Zemax aperture type enum.')

    aperture.ApertureType = aperture_type
    aperture.ApertureValue = f_number
    return aperture_name, aperture.ApertureValue


def ensure_surface_count(lde, surface_count):
    """Keep OBJ, requested sequential surfaces, and IMS."""
    while int(lde.NumberOfSurfaces) < surface_count:
        lde.InsertNewSurfaceAt(int(lde.NumberOfSurfaces) - 1)
    while int(lde.NumberOfSurfaces) > surface_count:
        lde.RemoveSurfaceAt(2)
    return [lde.GetSurfaceAt(i) for i in range(surface_count)]


def make_surface_stop(surface):
    if hasattr(surface, 'MakeSurfaceStop'):
        surface.MakeSurfaceStop()
    else:
        surface.IsStop = True


def make_radius_variable(surface):
    if not hasattr(surface, 'RadiusCell'):
        raise RuntimeError(f'Surface {surface.SurfaceNumber} does not expose RadiusCell.')
    surface.RadiusCell.MakeSolveVariable()


def make_thickness_variable(surface):
    if not hasattr(surface, 'ThicknessCell'):
        raise RuntimeError(f'Surface {surface.SurfaceNumber} does not expose ThicknessCell.')
    surface.ThicknessCell.MakeSolveVariable()


def make_thickness_marginal_ray_height(surface, zosapi):
    if not hasattr(surface, 'ThicknessCell'):
        raise RuntimeError(f'Surface {surface.SurfaceNumber} does not expose ThicknessCell.')
    solve_data = surface.ThicknessCell.CreateSolveType(zosapi.Editors.SolveType.MarginalRayHeight)
    surface.ThicknessCell.SetSolveData(solve_data)
    return solve_data


def get_solve_settings(solve_data, primary_name, aliases=None):
    aliases = aliases or []
    for attr_name in [primary_name] + aliases:
        if hasattr(solve_data, attr_name):
            return getattr(solve_data, attr_name)
    available = [name for name in dir(solve_data) if 'Pickup' in name or name.startswith('_S_')]
    raise RuntimeError(
        f'Cannot find solve settings {primary_name}. Available pickup-like members: {available}'
    )


def set_existing_solve_value(settings, names, value):
    for name in names:
        if hasattr(settings, name):
            setattr(settings, name, value)
            return name
    return None


def make_surface_pickup(cell, zosapi, pickup_surface, scale=1.0, offset=0.0, column=None):
    """
    Apply a Lens Data Editor Surface Pickup solve.

    This is the ZOS-API form of:
        SOLVETYPE surf, CP/TP/SP/etc., pickup_surface, scale, offset, column

    Pass the exact LDE cell to edit, for example surface.RadiusCell or
    surface.ThicknessCell. Leave column=None for normal same-column pickup,
    matching radius-to-radius or thickness-to-thickness pickup.
    """
    solve_data = cell.CreateSolveType(zosapi.Editors.SolveType.SurfacePickup)
    pickup_data = get_solve_settings(
        solve_data,
        '_S_SurfacePickup',
        aliases=[
            'S_SurfacePickup',
            '_S_SurfacePickup_',
            'S_SurfacePickup_',
            '_S_Pickup',
            'S_Pickup',
        ],
    )

    if set_existing_solve_value(pickup_data, ['Surface'], int(pickup_surface)) is None:
        raise RuntimeError('Surface Pickup solve data does not expose a Surface field.')
    set_existing_solve_value(pickup_data, ['ScaleFactor', 'Scale'], float(scale))
    set_existing_solve_value(pickup_data, ['Offset'], float(offset))
    if column is not None:
        set_existing_solve_value(pickup_data, ['Column', 'ColumnNumber'], column)

    cell.SetSolveData(solve_data)
    return solve_data


def set_first_available_material(surface, material_names):
    last_error = None
    for material_name in material_names:
        try:
            surface.Material = material_name
            return material_name
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f'Cannot set material from {material_names}: {last_error}')
