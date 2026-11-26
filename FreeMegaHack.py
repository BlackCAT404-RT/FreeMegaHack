r"""-- MegaHack Crack by BlackCAT404 --"""

import platform
import sys
import atexit

_PAUSED = False

def _pause(msg="\nPress Enter to exit..."):
    global _PAUSED
    if _PAUSED:
        return
    _PAUSED = True
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        pass
    except Exception:
        pass

if "--no-pause" not in sys.argv:
    atexit.register(_pause)

err = lambda msg: print(f"[ERROR] {msg}") or exit(1)
warn = lambda msg: print(f"[WARNING] {msg}")

if platform.system().lower() != 'windows':
    err(f"This crack is meant for windows versions of Mega Hack. {platform.system()} is not supported.")

# Get selected version from cli
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--mh-version', default='latest', help='Specify version (default: latest)')
parser.add_argument('--standalone', action='store_true', help='Set if selected version should be a standalone version')
parser.add_argument('--no-pause', action='store_true', help='Do not wait for Enter at the end')

args = parser.parse_args()
MH_VERSION = args.mh_version
USE_GEODE = not args.standalone # skip entries that have `geode: true`

# Find Geometry Dash's installation directory
from pathlib import Path
import winreg
import os
import re

def get_steam_path():
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
        return Path(winreg.QueryValueEx(key, "InstallPath")[0])
    except FileNotFoundError:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
            return Path(winreg.QueryValueEx(key, "InstallPath")[0])
        except FileNotFoundError:
            err("Unable to find Steam installation directory in your registry")

def get_steam_libraries(steam_path: Path):
    libraries = [steam_path]
    vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"

    if vdf_path.exists():
        content = vdf_path.read_text(encoding='utf-8')
        # Find all "path" entries
        paths = re.findall(r'"path"\s+"([^"]+)"', content)
        libraries.extend(map(Path, paths))

    return libraries

def find_game(app_id) -> Path | None:
    steam_path = get_steam_path()
    print(f"Got a steam installation path of '{steam_path}'")

    for library in get_steam_libraries(steam_path):
        manifest = library / "steamapps" / f"appmanifest_{app_id}.acf"
        if manifest.exists():
            content = manifest.read_text(encoding='utf-8')
            match = re.search(r'"installdir"\s+"([^"]+)"', content)
            if match:
                return library / "steamapps" / "common" / match.group(1)

    return None

# Geometry Dash's steamid is 322170
GD_PATH = find_game("322170")

if GD_PATH is None:
    err("Unable to find where Geometry Dash is installed")

# Sanity check
if not (GD_PATH / "GeometryDash.exe").exists():
    err(f"GeometryDash.exe not found in expected path at '{GD_PATH}'")

print(f"Found Geometry Dash installation at '{GD_PATH}'")

# MegaHack uses SHGetKnownFolderPath to find the local appdata directory. If it fails we can fall back to using the environment variable.
import ctypes
import uuid
import os

FOLDERID_LocalAppData =  uuid.UUID("{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}").bytes_le
appdata_dir_buf = ctypes.c_wchar_p()

if ctypes.windll.shell32.SHGetKnownFolderPath(
    ctypes.byref(ctypes.create_string_buffer(FOLDERID_LocalAppData, 16)),
    0, 0,
    ctypes.byref(appdata_dir_buf)
):
    warn("Failed to find the local appdata directory using SHGetKnownFolderPath. Trying %LOCALAPPDATA%.")
    LOCALAPPDATA = os.getenv("LOCALAPPDATA", None)
    if not LOCALAPPDATA:
        err("Unable to find the local AppData directory with SHGetKnownFolderPath or %LOCALAPPDATA%. Aborting.")
else:
    LOCALAPPDATA = appdata_dir_buf.value

LOCALAPPDATA = Path(LOCALAPPDATA)
print(f"Found the local appdata directory at '{LOCALAPPDATA!s}'")

# the rest of the shit we need
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from textwrap import dedent
from contextlib import contextmanager
import zipfile
import io
import json
import re
import time
import base64
import functools
import shutil
import tempfile

# ---------------------------------------------------------------------------
# STABLE WORKING DIRECTORY
# Under PyInstaller, __file__ lives in the temporary _MEIPASS folder that is
# deleted on exit. Use the .exe's own folder instead, with a writable fallback.
# ---------------------------------------------------------------------------
def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent
    else:
        candidate = Path(__file__).resolve().parent

    try:
        probe = candidate / ".mh_write_test"
        probe.write_bytes(b"x")
        probe.unlink()
        return candidate
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "megahack_crack"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

CWD = get_base_dir()
os.chdir(str(CWD))
print(f"Working directory: '{CWD!s}'")
print = functools.partial(print, flush=True)

def get_terminal_width():
    try:
        size = shutil.get_terminal_size()
        return size.columns - 1
    except OSError:
        # Fallback if the terminal size cannot be determined
        return 80

# ---------------------------------------------------------------------------
# FORCED COPY WITH REPLACEMENT
# Overwrites the destination, clears read-only, retries a few times.
# Returns True only if the destination exists with the expected size.
# ---------------------------------------------------------------------------
def force_copy(src: Path, dst: Path) -> bool:
    src = Path(src)
    dst = Path(dst)
    if not src.exists():
        warn(f"Source file missing, cannot copy: '{src!s}'")
        return False

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        warn(f"Cannot create folder '{dst.parent!s}': {e}")
        return False

    try:
        if dst.exists():
            try:
                os.chmod(dst, 0o666)
            except OSError:
                pass
            dst.unlink()
    except OSError:
        pass  # copyfile will attempt the overwrite anyway

    for _ in range(3):
        try:
            shutil.copyfile(src, dst)
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                return True
        except OSError as e:
            last = e
            time.sleep(0.3)
    else:
        try:
            warn(f"Copy failed '{src!s}' -> '{dst!s}': {last}")
        except UnboundLocalError:
            warn(f"Copy failed '{src!s}' -> '{dst!s}'")
        return False

@contextmanager
def progress_log(msg: str):
    print(msg, end="... ")
    success = False
    try:
        yield
        success = True
    finally:
        print("Done!" if success else "Failed.")

# Download selected version

# json containing all megahack version and information
INSTALL_JSON_URL = "https://absolllute.com/api/mega_hack/v9/install.json"

# absolllute.com blocks user agents containing `Python-urllib` lmfao
# if the empty UA ever starts 403'ing, just copy one from online somewhere
USER_AGENT = ""

r = urlopen(Request(INSTALL_JSON_URL, headers={"User-Agent": USER_AGENT}))
if r.status != 200:
    err(f"Unable to get installation json. Status Code: {r.status}")

cur_package = json.load(r)["packages"][0]
if cur_package["name"] != "Mega Hack v9":
    warn(f"This was tested for Mega Hack v9, most recent version seems to now be {cur_package['name']}")

def find_bundle(bundles: list[dict]):
    global MH_VERSION, USE_GEODE
    if MH_VERSION == 'latest':
        return bundles[0]

    found_other = False
    for bundle in bundles:
        if bundle["name"] == MH_VERSION:
            if bundle["geode"] != USE_GEODE:
                found_other = True
            else:
                return bundle

    if found_other:
        if USE_GEODE:
            warn(f"Found entry for '{MH_VERSION}' but it was the standalone version. Try rerunning with `--standalone`")
        else:
            warn(f"Found entry for '{MH_VERSION}' but it was the geode version. Try rerunning without `--standalone`")

    return None

cur_bundle = find_bundle(cur_package["bundles"])
if not cur_bundle:
    err(f"Unable to find bundle information for '{MH_VERSION}' ({'GEODE' if USE_GEODE else 'NON-GEODE'})")

# resolve 'latest' to a real version so string comparisons in patch_dll work
if MH_VERSION == 'latest':
    MH_VERSION = cur_bundle["name"]

group = cur_bundle["group"]
filename = cur_bundle["file"]

MEGAHACK_URL = "https://absolllute.com/api/mega_hack/v9/files/{}/{}".format(group, filename)

with progress_log(f"Downloading {cur_bundle['name']}"):
    try:
        with urlopen(Request(MEGAHACK_URL, headers={"User-Agent": USER_AGENT})) as r:
            megahack_zip = r.read()
    except HTTPError as e:
        err(f"HTTP error: {e.code}")
    except URLError as e:
        err(f"URL error: {e.reason} - {str(e)}")

# Patch information
# Patterns tested on v9.0.3, v9.0.7, v9.0.9, v9.0.11, and v9.1.0

# 56 57 48 83 EC ? 48 83 79 10 40
# patch id verification
ID_CHECK_PAT = re.compile(rb'\x56\x57\x48\x83\xEC.\x48\x83\x79\x10\x40', re.DOTALL | re.MULTILINE)
# 55 41 56 56 57 53 48 83 EC ? 48 8D 6C 24 ? 48 C7 45 ? ? ? ? ? ? ? ? ? 0F 84 ? ? ? ? 4C 89 C7
# patch json signature verification
JSON_SIGNATURE_CHECK_PAT = re.compile(rb'\x55\x41\x56\x56\x57\x53\x48\x83\xEC.\x48\x8D\x6C\x24.\x48\xC7\x45.........\x0F\x84....\x4C\x89\xC7', re.DOTALL | re.MULTILINE)
# ? 10 00 00 00 E8 ? ? ? ? 48 83 7F
# patch out checksum result of hardware manufacturer to make the key 0x00000000 no matter what
KEY_BYBASS_PAT = re.compile(rb'(?<=.\x10\x00\x00\x00)\xE8....(?=\x48\x83\x7F)', re.DOTALL | re.MULTILINE)
# 55 41 57 41 56 56 57 53 48 81 EC ? ? ? ? 48 8D AC 24 ? ? ? ? 48 C7 85 ? ? ? ? ? ? ? ? 48 89 D7 48 89 CB
# patch out the function that verifies your login is legit
BYPASS_VERIFY_PAT = re.compile(br'\x55\x41\x57\x41\x56\x56\x57\x53\x48\x81\xEC....\x48\x8D\xAC\x24....\x48\xC7\x85........\x48\x89\xD7\x48\x89\xCB', re.MULTILINE | re.DOTALL)

# the first two functions we need to patch involve forcing it to return 1 lol
PATCH_DATA1 = b"".join([
    b"\xb8\x01\x00\x00\x00", # mov eax, 1
    b"\xc3", # ret
])

# overwriting the function call to instead just set rax to 0
PATCH_DATA2 = b"".join([
    b"\xb8\x00\x00\x00\x00", # mov eax, 0
])

# void function, instant return here
PATCH_DATA3 = b"".join([
    b"\xc3", # ret
])

def patch_dll(data: bytes):
    def apply_patch(pattern, patch, min_version=None):
        nonlocal data
        if min_version and MH_VERSION < min_version:
            # No need to apply
            return True

        return data != (data := pattern.sub(lambda m: patch + m.group(0)[len(patch):], data, 1))

    if not apply_patch(ID_CHECK_PAT, PATCH_DATA1):
        err("Failed to find pattern for the id check!")
    if not apply_patch(JSON_SIGNATURE_CHECK_PAT, PATCH_DATA1):
        err("Failed to find pattern for the json signature check!")
    if not apply_patch(KEY_BYBASS_PAT, PATCH_DATA2):
        err("Failed to find pattern for the key bypass!")
    if not apply_patch(BYPASS_VERIFY_PAT, PATCH_DATA3, "v9.1"):
        err("Failed to find pattern for the verification bypass!")

    return data

def handle_standalone():
    # Extract the zip
    with progress_log("Extracting zip file and patching"):
        with zipfile.ZipFile(io.BytesIO(megahack_zip), 'r') as zf:
            # Patching and unpacking shit
            for item in zf.infolist():
                filename = item.filename

                # Directories always come before the contents within the directories, so it's safe to extract sequentially
                if filename.endswith("/"):
                    (GD_PATH / filename.rstrip("/")).mkdir(parents=True, exist_ok=True)
                else:
                    data = zf.read(filename)
                    match filename:
                        case "hackpro.dll":
                            data = patch_dll(data)

                    (GD_PATH / item.filename).write_bytes(data)

    BORDER = '#' * get_terminal_width()
    return dedent(f"""
        {BORDER}
        Cracking process finished!
        * The license file was created in {mh_local_dir} and {CWD}.
        * If you don't see the license file in {mh_local_dir}, copy the one in {CWD} to there.
        {BORDER}
    """)

def handle_geode():
    OUT_FILENAME = "absolllute.hackmega.geode"
    out_path = CWD / OUT_FILENAME  # stable location next to the .exe

    with progress_log("Extracting geode file and patching"):
        with zipfile.ZipFile(io.BytesIO(megahack_zip), 'r') as zip_in, \
            zipfile.ZipFile(out_path, 'w') as zip_out:

            # Patching shit
            for item in zip_in.infolist():
                filename = item.filename
                data = zip_in.read(filename)

                match filename:
                    case "absolllute.megahack.dll":
                        data = patch_dll(data)

                        # need to update the filename too
                        item.filename = OUT_FILENAME.replace(".geode", ".dll")
                    case "mod.json":
                        # we need to modify the id to match the output filename, all the other changes are cosmetic
                        mod = json.loads(data)
                        mod["id"] = "absolllute.hackmega"
                        mod["name"] = "HackMega"
                        mod["description"] = "Totally new software..."
                        data = json.dumps(mod, indent="\t").encode()

                zip_out.writestr(item, data)

    # Force-transfer it over to the geode folder now (create folder, replace existing)
    GEODE_DIR = GD_PATH / "geode" / "mods"
    copied_geode = False
    with progress_log("Copying geode to mods folder (overwrite)"):
        copied_geode = force_copy(out_path, GEODE_DIR / OUT_FILENAME)

    if not copied_geode:
        warn(f"Could not copy the .geode into '{GEODE_DIR!s}'. The file is kept at '{out_path!s}' — copy it manually after installing Geode.")

    geode_msg = (
        f"* The cracked geode was written to {GEODE_DIR / OUT_FILENAME} (replaced if it existed). You should be able to open the game and press tab to see the mod menu!"
        if copied_geode else
        f"* Geode was not copied. After installing geode, copy '{out_path!s}' into '{GEODE_DIR!s}' manually."
    )

    BORDER = '#' * get_terminal_width()
    return dedent(f"""
        {BORDER}
        Cracking process finished!
        * The license file was created in {mh_local_dir} and {CWD}.
        * If you don't see the license file in {mh_local_dir}, copy the one in {CWD} to there.
        {geode_msg}
        {BORDER}
    """)



# Write a now valid license to the expected directory
with progress_log("Creating fake license file"):
    mh_local_dir = LOCALAPPDATA / "absolllute.megahack"
    mh_local_dir.mkdir(parents=True, exist_ok=True)
    mh_license_path = mh_local_dir / "license"
    mh_license_fallback_path = CWD / "license"

    EXPECTED_CHACHA_KEY = bytes.fromhex("0E 84 1F A5 BF E5 CE 8F C9 1E B1 1A DD 1D CE F6 94 04 5B EE AF CF 52 1B F4 34 1D 39 97 C1 C2 19")

    def random_hex(length):
        assert length % 2 == 0
        return os.urandom(length // 2).hex().upper()

    signature = os.urandom(256) # we bypass this check, so just set it to whatever
    identifier = random_hex(64) # this is possible to generate legitamately, but it really bloats the code bc it involves a lot of winapi stuff
    token = random_hex(32) # honestly, I have no idea what this is for, it's not used anywhere from what I can tell
    secret = random_hex(32) # same with this, couldn't find anywhere that reads this

    data = {
        "id": identifier,
        "token": token,
        "secret": secret,
        "timestamp": str(int(time.time())),
        # this is used to decrypt some resources or something else important (didn't really dig into it) but it's requried to be this
        "guid2": EXPECTED_CHACHA_KEY.hex().upper()
    }

    data_dump = json.dumps(data, separators=(",", ":"))

    license = {
        "data": base64.b64encode(data_dump.encode()).decode('utf-8'),
        "sig": base64.b64encode(signature).decode('utf-8'),
        "token": token
    }

    license_str = json.dumps(license, separators=(",", ":"))

    # primary copy in CWD, then force-replace into %LocalAppData%\absolllute.megahack
    mh_license_fallback_path.write_text(license_str)
    if not force_copy(mh_license_fallback_path, mh_license_path):
        warn(f"Could not write the license to '{mh_license_path!s}'. Copy '{mh_license_fallback_path!s}' there manually.")

    assert mh_license_path.exists() or mh_license_fallback_path.exists()

# Yay all done, past this point is just printing stuff to make it nice and pretty

print(handle_geode() if USE_GEODE else handle_standalone())
