import os
import sys
import winreg

# This boilerplate requires the 'pythonnet' module.
# Install it with:
#     python -m pip install pythonnet
# Use the same Python interpreter that runs this script.
try:
    import clr
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Missing pythonnet module. Install it with 'python -m pip install pythonnet' "
        f"using the same Python executable: {sys.executable}"
    ) from exc

def find_zemax_root():
    """Find the Zemax data root that contains ZOSAPI_NetHelper.dll."""
    registry_locations = [
        (winreg.HKEY_CURRENT_USER, r"Software\Zemax"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Zemax"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Zemax"),
    ]
    for hive, subkey in registry_locations:
        key = None
        try:
            key = winreg.OpenKey(
                winreg.ConnectRegistry(None, hive),
                subkey,
                0,
                winreg.KEY_READ,
            )
            value, _ = winreg.QueryValueEx(key, 'ZemaxRoot')
            net_helper = os.path.join(value, r'ZOS-API\Libraries\ZOSAPI_NetHelper.dll')
            if os.path.exists(net_helper):
                return value
        except FileNotFoundError:
            pass
        finally:
            if key is not None:
                winreg.CloseKey(key)

    user_profile = os.environ.get('USERPROFILE', '')
    candidates = [
        os.path.join(user_profile, 'Documents', 'Zemax'),
        os.path.join(user_profile, 'Documents', 'Ansys Zemax'),
        r'C:\Users\Public\Documents\Zemax',
        r'C:\ProgramData\Zemax',
    ]
    for candidate in candidates:
        net_helper = os.path.join(candidate, r'ZOS-API\Libraries\ZOSAPI_NetHelper.dll')
        if os.path.exists(net_helper):
            return candidate

    searched = ', '.join([path for _, path in registry_locations])
    raise FileNotFoundError(
        "Cannot find ZemaxRoot or ZOSAPI_NetHelper.dll. "
        f"Searched registry keys: {searched}; common data folders: {candidates}"
    )


# determine the Zemax working directory
zemax_root = find_zemax_root()
NetHelper = os.path.join(zemax_root, r'ZOS-API\Libraries\ZOSAPI_NetHelper.dll')
if not os.path.exists(NetHelper):
    raise FileNotFoundError(f"ZOSAPI_NetHelper.dll not found at expected location: {NetHelper}")

# add the NetHelper DLL for locating the OpticStudio install folder
clr.AddReference(NetHelper)
import ZOSAPI_NetHelper

pathToInstall = ''
# uncomment the following line to use a specific instance of the ZOS-API assemblies
# pathToInstall = r'C:\Program Files\Zemax OpticStudio'

# connect to OpticStudio
success = ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(pathToInstall)
zemaxDir = ''
if success:
    zemaxDir = ZOSAPI_NetHelper.ZOSAPI_Initializer.GetZemaxDirectory()
    print(f'Found OpticStudio at: {zemaxDir}')
else:
    raise Exception('Cannot find OpticStudio. Verify OpticStudio is installed and the Zemax registry key is correct.')

# load the ZOS-API assemblies
zosapi_dll = os.path.join(zemaxDir, 'ZOSAPI.dll')
zosapi_interfaces_dll = os.path.join(zemaxDir, 'ZOSAPI_Interfaces.dll')
for path in (zosapi_dll, zosapi_interfaces_dll):
    if not os.path.exists(path):
        raise FileNotFoundError(f'Expected ZOSAPI assembly not found: {path}')

clr.AddReference(zosapi_dll)
clr.AddReference(zosapi_interfaces_dll)
import ZOSAPI

from optimization_settings import add_merit_operand, clear_merit_function
from system_settings import (
    ensure_surface_count,
    make_radius_variable,
    make_surface_pickup,
    make_surface_stop,
    make_thickness_marginal_ray_height,
    make_thickness_variable,
    set_angle_fields,
    set_aperture_to_paraxial_working_f_number,
    set_first_available_material,
    set_primary_wavelength,
)

TheConnection = ZOSAPI.ZOSAPI_Connection()
if TheConnection is None:
    raise Exception('Unable to initialize NET connection to ZOSAPI')

TheApplication = TheConnection.ConnectAsExtension(0)
if TheApplication is None:
    raise Exception('Unable to acquire ZOSAPI application')

if not TheApplication.IsValidLicenseForAPI:
    raise Exception(
        "License is not valid for ZOSAPI use. "
        "Make sure you have enabled 'Programming > Interactive Extension' from the OpticStudio GUI."
    )

TheSystem = TheApplication.PrimarySystem
if TheSystem is None:
    raise Exception('Unable to acquire Primary system')

print('Connected to OpticStudio')
print('Serial #: ', TheApplication.SerialCode)

def setup_periscopic_lens(system, zosapi):
    efl_target = 200.0
    lens_spacing = 180.0
    half_lens_spacing = lens_spacing / 2.0
    optical_power_plus = 0.0073
    optical_power_minus = 0.0038
    optical_power = optical_power_minus
    wavelength_um = 0.55
    n_sf2 = 1.65174
    radius = 2.0 * (n_sf2 - 1.0) / optical_power
    glass_thickness = 15.0
    paraxial_working_f_number = 10.0
    object_image_distance = 800.0
    field_angles = [0.0, 10.5, 15.0]

    system.New(False)
    lde = system.LDE
    obj, f1_front, f1_back, stop, f2_front, f2_back, image = ensure_surface_count(lde, 7)

    set_primary_wavelength(system, wavelength_um)
    field_type_name = set_angle_fields(system, zosapi, field_angles)
    aperture_name, aperture_value = set_aperture_to_paraxial_working_f_number(
        system,
        zosapi,
        paraxial_working_f_number,
    )

    obj.Comment = 'Finite object'
    obj.Thickness = object_image_distance

    f1_front.Comment = 'First SF2 lens front'
    f1_front.Radius = radius
    f1_front.Thickness = glass_thickness
    material_name = set_first_available_material(f1_front, ['SF2', 'N-SF2'])

    f1_back.Comment = 'First SF2 lens back'
    f1_back.Radius = -radius
    f1_back.Thickness = half_lens_spacing

    stop.Comment = 'STOP / pickup surface 2 thickness'
    stop.Thickness = half_lens_spacing
    make_surface_stop(stop)

    f2_front.Comment = 'Second SF2 lens front / pickup'
    f2_front.Radius = radius
    f2_front.Thickness = glass_thickness
    material_name_2 = set_first_available_material(f2_front, ['SF2', 'N-SF2'])

    f2_back.Comment = 'Second SF2 lens back / pickup'
    f2_back.Radius = -radius
    f2_back.Thickness = object_image_distance

    image.Comment = 'Unit-magnification image'

    make_radius_variable(f1_front)
    make_radius_variable(f1_back)
    make_thickness_variable(obj)
    make_thickness_variable(f1_back)

    make_surface_pickup(stop.ThicknessCell, zosapi, f1_back.SurfaceNumber, scale=1.0)
    make_surface_pickup(f2_front.RadiusCell, zosapi, f1_back.SurfaceNumber, scale=-1.0)
    make_surface_pickup(f2_front.ThicknessCell, zosapi, f1_front.SurfaceNumber, scale=1.0)
    make_surface_pickup(f2_back.RadiusCell, zosapi, f1_front.SurfaceNumber, scale=-1.0)
    make_thickness_marginal_ray_height(f2_back, zosapi)

    mfe = system.MFE
    clear_merit_function(mfe)
    add_merit_operand(mfe, zosapi, 'EFFL', efl_target, 1.0)
    add_merit_operand(mfe, zosapi, 'PMAG', -1.0, 1.0)

    merit_value = mfe.CalculateMeritFunction()
    system.UpdateStatus()

    print('Periscopic symmetric SF2 lens setup complete.')
    print(f'  Target EFFL: {efl_target:.6g} mm')
    print(f'  Lens spacing: {lens_spacing:.6g} mm = surface 2 thickness {half_lens_spacing:.6g} + STOP thickness pickup')
    print(f'  Phi candidates: F+={optical_power_plus:.6g}, F-={optical_power_minus:.6g}; selected {optical_power:.6g}')
    print(f'  Combined phi: {2.0 * optical_power - lens_spacing * optical_power * optical_power:.8g} 1/mm')
    print(f'  Wavelength: {wavelength_um:.6g} um')
    print(f'  Material: first={material_name}, second={material_name_2}')
    print(f'  SF2 index used for initial radius: {n_sf2:.6g}')
    print(f'  Initial equal-convex radius: {radius:.6g} mm')
    print(f'  Glass thickness: {glass_thickness:.6g} mm')
    print(f'  Initial object/image distance: {object_image_distance:.6g} mm')
    print(f'  Fields ({field_type_name}): {field_angles}')
    print(f'  System aperture: {aperture_name} = {aperture_value:.6g}')
    print('  Surface semi-diameter/mechanical aperture constraints: not set')
    print(
        f'  Variables: surface {obj.SurfaceNumber} thickness, '
        f'surface {f1_front.SurfaceNumber} radius, surface {f1_back.SurfaceNumber} radius, '
        f'surface {f1_back.SurfaceNumber} thickness'
    )
    print(
        '  Pickup solves equivalent to: '
        f'SOLVETYPE {stop.SurfaceNumber}, TP, {f1_back.SurfaceNumber}, 1; '
        f'SOLVETYPE {f2_front.SurfaceNumber}, CP, {f1_back.SurfaceNumber}, -1; '
        f'SOLVETYPE {f2_front.SurfaceNumber}, TP, {f1_front.SurfaceNumber}, 1; '
        f'SOLVETYPE {f2_back.SurfaceNumber}, CP, {f1_front.SurfaceNumber}, -1; '
        f'SOLVETYPE {f2_back.SurfaceNumber}, TM, 0'
    )
    print('  Merit operands: row 1 EFFL=200, row 2 PMAG=-1')
    print(f'  Merit function value: {merit_value:.6g}')


setup_periscopic_lens(TheSystem, ZOSAPI)
