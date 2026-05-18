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

# determine the Zemax working directory
try:
    aKey = winreg.OpenKey(
        winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER),
        r"Software\Zemax",
        0,
        winreg.KEY_READ,
    )
    zemaxData = winreg.QueryValueEx(aKey, 'ZemaxRoot')
finally:
    winreg.CloseKey(aKey)

NetHelper = os.path.join(zemaxData[0], r'ZOS-API\Libraries\ZOSAPI_NetHelper.dll')
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

# Insert Code Here
