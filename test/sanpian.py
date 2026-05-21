import os
import sys
import winreg
from itertools import islice

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


def reshape(data, x, y, transpose=False):
    """Converts a System.Double[,] to a 2D list for plotting or post processing."""
    if not isinstance(data, list):
        data = list(data)
    var_lst = [y] * x
    it = iter(data)
    res = [list(islice(it, i)) for i in var_lst]
    if transpose:
        return transpose(res)
    return res


def transpose(data):
    """Transposes a 2D list."""
    if not isinstance(data, list):
        data = list(data)
    return list(map(list, zip(*data)))

print('Connected to OpticStudio')
print('Serial #: ', TheApplication.SerialCode)

def first_existing_attr(obj, names):
    """Return the first existing enum/member value from a list of possible API names."""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name), name
    return None, None


def set_aperture_to_f_number(system, zosapi, f_number, efl):
    """Set aperture to image-space F/# where available, otherwise use EPD = EFL / F#."""
    aperture = system.SystemData.Aperture
    aperture_type, aperture_name = first_existing_attr(
        zosapi.SystemData.ZemaxApertureType,
        [
            'ImageSpaceFNumber',
            'ImageSpaceFNum',
            'ImageSpaceFNumberAndWorkingFNumber',
            'FloatByStopSize',
            'EntrancePupilDiameter',
        ],
    )
    if aperture_type is None:
        raise RuntimeError('Cannot find a supported Zemax aperture type enum.')

    aperture.ApertureType = aperture_type
    if aperture_name == 'EntrancePupilDiameter':
        aperture.ApertureValue = efl / f_number
    elif aperture_name == 'FloatByStopSize':
        aperture.ApertureValue = efl / (2.0 * f_number)
    else:
        aperture.ApertureValue = f_number
    return aperture_name, aperture.ApertureValue


def ensure_four_surface_single_lens(lde):
    """Keep OBJ, front lens/stop, back lens, IMS."""
    while int(lde.NumberOfSurfaces) < 4:
        lde.InsertNewSurfaceAt(int(lde.NumberOfSurfaces) - 1)
    while int(lde.NumberOfSurfaces) > 4:
        lde.RemoveSurfaceAt(2)
    return (
        lde.GetSurfaceAt(0),
        lde.GetSurfaceAt(1),
        lde.GetSurfaceAt(2),
        lde.GetSurfaceAt(3),
    )


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


def set_first_available_material(surface, material_names):
    last_error = None
    for material_name in material_names:
        try:
            surface.Material = material_name
            return material_name
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f'Cannot set material from {material_names}: {last_error}')


def clear_merit_function(mfe):
    count = int(mfe.NumberOfOperands)
    if count > 0:
        mfe.RemoveOperandsAt(1, count)


def add_merit_operand(mfe, zosapi, operand_name, target, weight=1.0):
    operand_type = getattr(zosapi.Editors.MFE.MeritOperandType, operand_name)
    operand = mfe.AddOperand()
    operand.ChangeType(operand_type)
    operand.Target = target
    operand.Weight = weight
    return operand


def setup_single_bk7_lens(system, zosapi):
    efl_target = 100.0
    optical_power = 0.01
    f_number = 4.0
    n_bk7 = 1.5168
    radius = 2.0 * (n_bk7 - 1.0) / optical_power
    lens_thickness = 7.0

    system.New(False)
    lde = system.LDE
    _, front, back, image = ensure_four_surface_single_lens(lde)

    aperture_name, aperture_value = set_aperture_to_f_number(
        system,
        zosapi,
        f_number,
        efl_target,
    )

    front.Comment = 'Front surface / STOP / BK7'
    front.Radius = radius
    front.Thickness = lens_thickness
    material_name = set_first_available_material(front, ['N-BK7', 'BK7'])
    front.SemiDiameter = efl_target / (2.0 * f_number)
    make_surface_stop(front)

    back.Comment = 'Back surface'
    back.Radius = -radius
    back.Thickness = efl_target
    back.SemiDiameter = efl_target / (2.0 * f_number)

    image.Comment = 'Image'

    make_radius_variable(front)
    make_radius_variable(back)
    make_thickness_variable(back)

    mfe = system.MFE
    clear_merit_function(mfe)
    effl = add_merit_operand(mfe, zosapi, 'EFFL', efl_target, 1.0)
    spha = add_merit_operand(mfe, zosapi, 'SPHA', 0.0, 1.0)

    merit_value = mfe.CalculateMeritFunction()
    system.UpdateStatus()

    print('Single BK7 lens setup complete.')
    print(f'  Target EFFL: {efl_target:.6g} mm')
    print(f'  Optical power fai: {optical_power:.6g} 1/mm')
    print(f'  F/#: {f_number:.6g}')
    print(f'  Material: {material_name}')
    print(f'  BK7 index used for initial radius: {n_bk7:.6g}')
    print(f'  Initial R1/R2: {front.Radius:.6g} / {back.Radius:.6g} mm')
    print(f'  Lens thickness: {front.Thickness:.6g} mm')
    print(f'  Aperture type/value: {aperture_name} / {aperture_value:.6g}')
    print(
        f'  Variables: surface {front.SurfaceNumber} radius, '
        f'surface {back.SurfaceNumber} radius, surface {back.SurfaceNumber} thickness'
    )
    print('  Merit operands: row 1 EFFL=100, row 2 SPHA=0')
    print(f'  Merit function value: {merit_value:.6g}')


setup_single_bk7_lens(TheSystem, ZOSAPI)
