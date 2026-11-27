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

import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--mh-version', default='latest', help='Specify version (default: latest)')
parser.add_argument('--standalone', action='store_true', help='Set if selected version should be a standalone version')
parser.add_argument('--no-pause', action='store_true', help='Do not wait for Enter at the end')

args = parser.parse_args()
MH_VERSION = args.mh_version
USE_GEODE = False

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

GD_PATH = find_game("322170")

if GD_PATH is None:
    err("Unable to find where Geometry Dash is installed")

if not (GD_PATH / "GeometryDash.exe").exists():
    err(f"GeometryDash.exe not found in expected path at '{GD_PATH}'")

print(f"Found Geometry Dash installation at '{GD_PATH}'")

def is_geode_installed() -> bool:
    if (GD_PATH / "geode").is_dir():
        return True
    if (GD_PATH / "geode-version").exists():
        return True
    try:
        if any(GD_PATH.glob("*eode*.dll")):
            return True
    except OSError:
        pass
    return False

if is_geode_installed():
    err("Geode detected in the game folder. This crack installs the standalone version, remove Geode first. Aborting before download and install.")

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
        return 80

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
        pass

    last = None
    for _ in range(3):
        try:
            shutil.copyfile(src, dst)
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                return True
        except OSError as e:
            last = e
            time.sleep(0.3)

    warn(f"Copy failed '{src!s}' -> '{dst!s}'" + (f": {last}" if last else ""))
    return False

def copy_tree_replace(src_dir: Path, dst_dir: Path) -> tuple[int, int]:
    ok = fail = 0
    for root, _dirs, files in os.walk(src_dir):
        rel = Path(root).relative_to(src_dir)
        target_dir = dst_dir / rel
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            warn(f"Cannot create folder '{target_dir!s}': {e}")
            fail += len(files)
            continue
        for name in files:
            if force_copy(Path(root) / name, target_dir / name):
                ok += 1
            else:
                fail += 1
    return ok, fail

@contextmanager
def progress_log(msg: str):
    print(msg, end="... ")
    success = False
    try:
        yield
        success = True
    finally:
        print("Done!" if success else "Failed.")

INSTALL_JSON_URL = "https://absolllute.com/api/mega_hack/v9/install.json"

USER_AGENT = ""

r = urlopen(Request(INSTALL_JSON_URL, headers={"User-Agent": USER_AGENT}))
if r.status != 200:
    err(f"Unable to get installation json. Status Code: {r.status}")

cur_package = json.load(r)["packages"][0]
if cur_package["name"] != "Mega Hack v9":
    warn(f"This was tested for Mega Hack v9, most recent version seems to now be {cur_package['name']}")

def find_bundle(bundles: list[dict]):
    global MH_VERSION, USE_GEODE

    def matches(bundle: dict) -> bool:
        return bool(bundle.get("geode")) == USE_GEODE

    if MH_VERSION == 'latest':
        for bundle in bundles:
            if matches(bundle):
                return bundle
        err(f"No {'GEODE' if USE_GEODE else 'STANDALONE'} bundle found in the package")

    found_other = False
    for bundle in bundles:
        if bundle["name"] == MH_VERSION:
            if not matches(bundle):
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

print(f"Selected bundle: {cur_bundle['name']} ({'GEODE' if cur_bundle['geode'] else 'STANDALONE'})")

if MH_VERSION == 'latest':
    MH_VERSION = cur_bundle["name"]

group = cur_bundle["group"]
filename = cur_bundle["file"]

MEGAHACK_URL = "https://absolllute.com/api/mega_hack/v9/files/{}/{}".format(group, filename)

with progress_log(f"Downloading {cur_bundle['name']} ({'geode' if cur_bundle['geode'] else 'standalone'})"):
    try:
        with urlopen(Request(MEGAHACK_URL, headers={"User-Agent": USER_AGENT})) as r:
            megahack_zip = r.read()
    except HTTPError as e:
        err(f"HTTP error: {e.code}")
    except URLError as e:
        err(f"URL error: {e.reason} - {str(e)}")

ID_CHECK_PAT = re.compile(rb'\x56\x57\x48\x83\xEC.\x48\x83\x79\x10\x40', re.DOTALL | re.MULTILINE)
JSON_SIGNATURE_CHECK_PAT = re.compile(rb'\x55\x41\x56\x56\x57\x53\x48\x83\xEC.\x48\x8D\x6C\x24.\x48\xC7\x45.........\x0F\x84....\x4C\x89\xC7', re.DOTALL | re.MULTILINE)
KEY_BYBASS_PAT = re.compile(rb'(?<=.\x10\x00\x00\x00)\xE8....(?=\x48\x83\x7F)', re.DOTALL | re.MULTILINE)
BYPASS_VERIFY_PAT = re.compile(br'\x55\x41\x57\x41\x56\x56\x57\x53\x48\x81\xEC....\x48\x8D\xAC\x24....\x48\xC7\x85........\x48\x89\xD7\x48\x89\xCB', re.MULTILINE | re.DOTALL)

PATCH_DATA1 = b"".join([
    b"\xb8\x01\x00\x00\x00",
    b"\xc3",
])

PATCH_DATA2 = b"".join([
    b"\xb8\x00\x00\x00\x00",
])

PATCH_DATA3 = b"".join([
    b"\xc3",
])

def patch_dll(data: bytes):
    def apply_patch(pattern, patch, min_version=None):
        nonlocal data
        if min_version and MH_VERSION < min_version:
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

def _ver_tuple(v) -> tuple[int, int, int]:
    parts = [int(x) for x in re.findall(r"\d+", str(v))][:3]
    return tuple(parts + [0] * (3 - len(parts)))

def _file_version(path: Path) -> str | None:
    try:
        import ctypes
        from ctypes import wintypes

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", wintypes.DWORD), ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD), ("dwFileVersionLS", wintypes.DWORD),
                ("dwProductVersionMS", wintypes.DWORD), ("dwProductVersionLS", wintypes.DWORD),
                ("dwFileFlagsMask", wintypes.DWORD), ("dwFileFlags", wintypes.DWORD),
                ("dwFileOS", wintypes.DWORD), ("dwFileType", wintypes.DWORD),
                ("dwFileSubtype", wintypes.DWORD), ("dwFileDateMS", wintypes.DWORD),
                ("dwFileDateLS", wintypes.DWORD),
            ]

        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buf):
            return None
        ptr = ctypes.c_void_p()
        length = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
            return None
        info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        return f"{info.dwFileVersionMS >> 16}.{info.dwFileVersionMS & 0xFFFF}.{info.dwFileVersionLS >> 16}"
    except Exception:
        return None

def _detect_version(version_files: list[Path], dll_patterns: list[str], dll_dirs: list[Path]) -> str | None:
    for p in version_files:
        try:
            if p.is_file():
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if re.fullmatch(r"\d+(\.\d+){0,2}", line):
                        return line
        except OSError:
            pass
    for d in dll_dirs:
        for pattern in dll_patterns:
            for p in sorted(d.glob(pattern)):
                v = _file_version(p)
                if v:
                    return v
    return None

def get_installed_geode_version() -> str | None:
    geode_dir = GD_PATH / "geode"
    return _detect_version(
        [geode_dir / "version", GD_PATH / "geode-version"],
        ["*eode*.dll"],
        [GD_PATH, geode_dir],
    )

def get_installed_gd_version() -> str | None:
    return _file_version(GD_PATH / "GeometryDash.exe")

def relax_requirements(mod: dict, installed_geode: str | None, installed_gd: str | None) -> list[str]:
    changes = []
    target_geode = installed_geode or "0.0.0"

    old = mod.get("geode")
    if str(old) != target_geode:
        changes.append(f"geode {old if old is not None else '(none)'} -> {target_geode}")
    mod["geode"] = target_geode

    if installed_gd:
        gd_req = mod.get("gd")
        if isinstance(gd_req, dict):
            for key, val in list(gd_req.items()):
                if _ver_tuple(val) > _ver_tuple(installed_gd):
                    changes.append(f"gd[{key}] {val} -> {installed_gd}")
                    gd_req[key] = installed_gd
            mod["gd"] = gd_req
        elif isinstance(gd_req, str) and _ver_tuple(gd_req) > _ver_tuple(installed_gd):
            changes.append(f"gd {gd_req} -> {installed_gd}")
            mod["gd"] = installed_gd

    deps = mod.get("dependencies")
    if isinstance(deps, dict):
        for key in list(deps):
            if str(key).lower() in {"geode", "geode.loader"}:
                if _ver_tuple(deps[key]) > _ver_tuple(target_geode):
                    changes.append(f"dependencies[{key}] {deps[key]} -> {target_geode}")
                    deps[key] = target_geode
    elif isinstance(deps, list):
        for dep in deps:
            if isinstance(dep, dict) and str(dep.get("id", "")).lower() in {"geode", "geode.loader"}:
                if _ver_tuple(dep.get("version", "0")) > _ver_tuple(target_geode):
                    changes.append(f"dependency {dep.get('id')} {dep.get('version')} -> {target_geode}")
                    dep["version"] = target_geode

    return changes

def handle_standalone():
    staging = Path(tempfile.mkdtemp(prefix="mh_stage_", dir=str(CWD)))

    try:
        with progress_log("Extracting zip file and patching"):
            with zipfile.ZipFile(io.BytesIO(megahack_zip), 'r') as zf:
                for item in zf.infolist():
                    filename = item.filename
                    dst = staging / filename

                    if filename.endswith("/"):
                        dst.mkdir(parents=True, exist_ok=True)
                        continue

                    data = zf.read(filename)
                    match filename.replace("\\", "/").rsplit("/", 1)[-1].lower():
                        case "hackpro.dll":
                            data = patch_dll(data)

                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(data)

        with progress_log("Copying dlls and icon folder into the game folder (overwrite)"):
            copied, failed = copy_tree_replace(staging, GD_PATH)

        if failed:
            warn(f"{failed} file(s) could not be copied. Copy them manually from '{staging!s}' if needed.")
        else:
            print(f"Copied {copied} file(s).")

        BORDER = '#' * get_terminal_width()
        return dedent(f"""
            {BORDER}
            Cracking process finished!
            * All Mega Hack files (dlls + icons) were copied into '{GD_PATH!s}' next to GeometryDash.exe, replacing existing ones.
            * The license file was created in {mh_local_dir}, {GD_PATH} and {CWD}.
            * If you don't see the license file in {mh_local_dir}, copy the one in {GD_PATH} to there.
            {BORDER}
        """)
    finally:
        if failed == 0:
            shutil.rmtree(staging, ignore_errors=True)

def handle_geode():
    OUT_FILENAME = "absolllute.hackmega.geode"
    out_path = CWD / OUT_FILENAME

    installed_geode = get_installed_geode_version()
    installed_gd = get_installed_gd_version()
    print(f"Installed Geode version: {installed_geode or 'not detected'}")
    print(f"Installed game version:  {installed_gd or 'not detected'}")

    saw_mod_json = False

    with progress_log("Extracting geode file and patching"):
        with zipfile.ZipFile(io.BytesIO(megahack_zip), 'r') as zip_in, \
            zipfile.ZipFile(out_path, 'w') as zip_out:

            for item in zip_in.infolist():
                filename = item.filename
                data = zip_in.read(filename)

                base = filename.lower().replace("\\", "/").rsplit("/", 1)[-1]

                if base == "absolllute.megahack.dll":
                    data = patch_dll(data)
                    item.filename = OUT_FILENAME.replace(".geode", ".dll")
                elif base == "mod.json":
                    saw_mod_json = True

                    mod = json.loads(data.decode("utf-8-sig"))
                    mod["id"] = "absolllute.hackmega"
                    mod["name"] = "HackMega"
                    mod["description"] = "Totally new software..."
                    mod.setdefault("developer", "absolllute")
                    mod.setdefault("version", "1.0.0")

                    for change in relax_requirements(mod, installed_geode, installed_gd):
                        warn(f"Relaxed requirement: {change}")

                    data = json.dumps(mod, indent="\t", ensure_ascii=False).encode()

                zip_out.writestr(item, data)

            if not saw_mod_json:
                warn("mod.json was not found in the package — injecting a minimal one")
                mod = {
                    "id": "absolllute.hackmega",
                    "name": "HackMega",
                    "developer": "absolllute",
                    "description": "Totally new software...",
                    "version": "1.0.0",
                    "geode": installed_geode or "0.0.0",
                    "gd": {"win": installed_gd} if installed_gd else {"win": "2.2.0"},
                }
                zip_out.writestr("mod.json", json.dumps(mod, indent="\t"))

    try:
        with zipfile.ZipFile(out_path) as zf:
            names = {n.lower().replace("\\", "/").rsplit("/", 1)[-1]: n for n in zf.namelist()}
            if "mod.json" not in names:
                warn("mod.json is missing from the produced .geode!")
            else:
                check = json.loads(zf.read(names["mod.json"]).decode("utf-8-sig"))
                print(f"Written requirement -> geode: {check.get('geode')!r}, gd: {check.get('gd')!r}, deps: {check.get('dependencies')!r}")
                if installed_geode and _ver_tuple(check.get("geode", "0")) > _ver_tuple(installed_geode):
                    warn(f"Requirement is STILL higher than the installed loader ({check.get('geode')} > {installed_geode})")
    except Exception as e:
        warn(f"Could not verify the produced .geode: {e}")

    GEODE_DIR = GD_PATH / "geode" / "mods"
    copied_geode = False

    with progress_log("Removing stale copies and Geode cache"):
        try:
            GEODE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        for stale in list(GEODE_DIR.glob("absolllute.*")):
            try:
                os.chmod(stale, 0o666)
            except OSError:
                pass
            try:
                stale.unlink()
            except OSError:
                pass
        for stale in (GEODE_DIR / ".index", GD_PATH / "geode" / "mods" / ".index"):
            try:
                stale.unlink()
            except OSError:
                pass
        shutil.rmtree(GD_PATH / "geode" / "config" / "absolllute.hackmega", ignore_errors=True)

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

with progress_log("Creating fake license file"):
    mh_local_dir = LOCALAPPDATA / "absolllute.megahack"
    mh_local_dir.mkdir(parents=True, exist_ok=True)
    mh_license_path = mh_local_dir / "license"
    mh_license_game_path = GD_PATH / "license"
    mh_license_fallback_path = CWD / "license"

    EXPECTED_CHACHA_KEY = bytes.fromhex("0E 84 1F A5 BF E5 CE 8F C9 1E B1 1A DD 1D CE F6 94 04 5B EE AF CF 52 1B F4 34 1D 39 97 C1 C2 19")

    def random_hex(length):
        assert length % 2 == 0
        return os.urandom(length // 2).hex().upper()

    signature = os.urandom(256)
    identifier = random_hex(64)
    token = random_hex(32)
    secret = random_hex(32)

    data = {
        "id": identifier,
        "token": token,
        "secret": secret,
        "timestamp": str(int(time.time())),
        "guid2": EXPECTED_CHACHA_KEY.hex().upper()
    }

    data_dump = json.dumps(data, separators=(",", ":"))

    license = {
        "data": base64.b64encode(data_dump.encode()).decode('utf-8'),
        "sig": base64.b64encode(signature).decode('utf-8'),
        "token": token
    }

    license_str = json.dumps(license, separators=(",", ":"))

    mh_license_fallback_path.write_text(license_str)
    if not force_copy(mh_license_fallback_path, mh_license_game_path):
        warn(f"Could not write the license to '{mh_license_game_path!s}'.")
    if not force_copy(mh_license_fallback_path, mh_license_path):
        warn(f"Could not write the license to '{mh_license_path!s}'. Copy '{mh_license_fallback_path!s}' there manually.")

    assert mh_license_path.exists() or mh_license_fallback_path.exists()

print(handle_geode() if USE_GEODE else handle_standalone())
