"""The only general-purpose project task entry point. Run from any directory."""

import argparse
import json
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import zlib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".scratch"
DOCS = {
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "TODO.md",
    "TASKS.md",
    "TASKS_DONE.md",
    "docs/architecture.md",
    "docs/decisions.md",
    "docs/runbook.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
}


def run(*args: str, cwd: Path = ROOT) -> None:
    executable = shutil.which(args[0]) or args[0]
    subprocess.run([executable, *args[1:]], cwd=cwd, check=True)


def frontend(*args: str) -> None:
    run("pnpm", *args, cwd=ROOT / "frontend")


def hygiene() -> None:
    result = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    paths = sorted(set(result.decode().strip("\0").split("\0")))
    errors = []
    for name in paths:
        if not name:
            continue
        file = ROOT / name
        if not file.is_file():
            continue
        if name.endswith(".md"):
            if name not in DOCS:
                errors.append(f"Unregistered document: {name}; update an existing canonical doc")
            if len(file.read_text(encoding="utf-8").splitlines()) > 220:
                errors.append(f"Document exceeds 220 lines: {name}")
        if name.startswith("tools/") and name != "tools/project.py":
            errors.append(f"Add a subcommand instead of another tool script: {name}")
        if name.endswith(".py") and not name.startswith(("backend/", "tools/")):
            errors.append(f"Python source outside its module or task entry point: {name}")
        if name.startswith((".scratch/", ".venv/")) or name.endswith((".db", ".sqlite")):
            errors.append(f"Local artifact tracked: {name}")
        if name.split("/")[-1].startswith(".env") and name != ".env.example":
            errors.append(f"Environment secrets file tracked: {name}")
    if errors:
        raise SystemExit("Repository hygiene failed:\n" + "\n".join(errors))
    print(f"Repository hygiene passed: {len(paths)} source paths, bounded docs/tools")


def export_schema() -> None:
    from research_platform.core.config import Settings
    from research_platform.main import create_app

    SCRATCH.mkdir(exist_ok=True)
    app = create_app(Settings(environment="test", database_url="sqlite://", _env_file=None))
    (SCRATCH / "openapi.json").write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def contract(check: bool = False) -> None:
    export_schema()
    if not check:
        frontend("run", "generate:api")
        return
    generated = SCRATCH / "schema.d.ts"
    frontend("exec", "openapi-typescript", "../.scratch/openapi.json", "-o", str(generated))
    committed = ROOT / "frontend/src/api/schema.d.ts"
    # Explicit UTF-8 on both sides: the default locale encoding is cp936/GBK on a
    # Chinese Windows install and cannot decode the Chinese error messages that
    # the OpenAPI schema now contains.
    if not committed.exists() or generated.read_text(encoding="utf-8") != committed.read_text(
        encoding="utf-8"
    ):
        raise SystemExit("API contract drift: run `uv run python tools/project.py contract`")


def migrate() -> None:
    from research_platform.core.config import Settings

    settings = Settings()
    url = settings.database_url.get_secret_value()
    if (
        settings.database_mysql
        or settings.environment == "production"
        or not url.startswith("sqlite:///")
    ):
        raise SystemExit("Automatic task migration is limited to the new local SQLite database")
    target = Path(url.removeprefix("sqlite:///"))
    if target.is_absolute() or not target.resolve().is_relative_to(SCRATCH.resolve()):
        raise SystemExit("Local database must be inside this project's .scratch directory")
    SCRATCH.mkdir(exist_ok=True)
    run("alembic", "-c", "backend/alembic.ini", "upgrade", "head")


def check_dev_ports(ports: tuple[int, ...] = (8000, 5173)) -> None:
    """Fail before starting children; leave an existing service untouched."""
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name == "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(
                    f"Development port {port} is unavailable; existing services were not stopped."
                ) from None


class WindowsProcessJob:
    """Own a Windows job that also claims descendants created after startup."""

    def __init__(self) -> None:
        self._handle = None
        self._close_handle = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            class IoCounters(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class BasicLimits(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class ExtendedLimits(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", BasicLimits),
                    ("IoInfo", IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel32.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                return
            # Closing the last job handle terminates every process still assigned.
            limits = ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x00002000
            if not kernel32.SetInformationJobObject(
                handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                kernel32.CloseHandle(handle)
                return
            self._handle = handle
            self._kernel32 = kernel32
            self._wintypes = wintypes
            self._close_handle = kernel32.CloseHandle
        except (AttributeError, OSError):
            self._handle = None

    def assign(self, process: subprocess.Popen) -> bool:
        if self._handle is None:
            return False
        return bool(
            self._kernel32.AssignProcessToJobObject(
                self._handle, self._wintypes.HANDLE(int(process._handle))
            )
        )

    def terminate(self) -> bool:
        if self._handle is None:
            return True
        return bool(self._kernel32.TerminateJobObject(self._handle, 1))

    def close(self) -> None:
        if self._handle is not None and self._close_handle is not None:
            self._close_handle(self._handle)
        self._handle = None


_WINDOWS_DEV_GATE = """\
import json
import subprocess
import sys

command = json.loads(sys.argv[1])
if sys.stdin.readline() != "start\\n":
    raise SystemExit(1)
try:
    target_stdin = open("CONIN$", "rb", buffering=0)
except OSError:
    target_stdin = None
raise SystemExit(subprocess.call(command, stdin=target_stdin))
"""


def _start_dev_child(
    command: list[str],
    *,
    cwd: Path,
    group_options: dict[str, object],
) -> subprocess.Popen:
    if os.name != "nt":
        return subprocess.Popen(command, cwd=cwd, **group_options)
    # Wait for the parent to assign this gate to the job before spawning descendants.
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            _WINDOWS_DEV_GATE,
            json.dumps(command, ensure_ascii=False),
        ],
        cwd=cwd,
        stdin=subprocess.PIPE,
        text=True,
        **group_options,
    )


def _open_dev_child_gate(process: subprocess.Popen) -> None:
    if os.name != "nt":
        return
    if process.stdin is None:
        raise OSError("development child start gate is unavailable")
    process.stdin.write("start\n")
    process.stdin.flush()
    process.stdin.close()


def _posix_process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_posix_process_group(process: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                process.wait(timeout=min(remaining, 0.1))
            except subprocess.TimeoutExpired:
                pass
        if not _posix_process_group_exists(process.pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def stop_dev_process(process: subprocess.Popen) -> bool:
    """Stop only the group created by this invocation, with a bounded fallback."""
    if os.name == "nt":
        if process.poll() is not None:
            return True
        try:
            # A dead leader is not signalled because its PID may have been reused.
            # The owning Windows job reclaims descendants after this helper returns.
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.wait(timeout=10)
            return True
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
            )
            if process.poll() is None:
                process.wait(timeout=5)
            return process.poll() is not None
        except (OSError, subprocess.TimeoutExpired):
            return False

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        pass
    else:
        if _wait_for_posix_process_group(process, 10):
            return True
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return _wait_for_posix_process_group(process, 5)


def dev() -> None:
    SCRATCH.mkdir(exist_ok=True)
    pnpm = shutil.which("pnpm")
    if not pnpm:
        raise SystemExit("pnpm is required; install the packageManager version from package.json")
    check_dev_ports()
    processes = []
    job = WindowsProcessJob() if os.name == "nt" else None
    group_options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    failure: BaseException | None = None
    try:
        api = _start_dev_child(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "research_platform.main:create_app",
                "--factory",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
            group_options=group_options,
        )
        processes.append(api)
        if job is not None and not job.assign(api):
            raise SystemExit("Cannot establish an owned process job for the API.")
        _open_dev_child_gate(api)
        web = _start_dev_child(
            [pnpm, "dev", "--port", "5173", "--strictPort"],
            cwd=ROOT / "frontend",
            group_options=group_options,
        )
        processes.append(web)
        if job is not None and not job.assign(web):
            raise SystemExit("Cannot establish an owned process job for the web server.")
        _open_dev_child_gate(web)
        print("Development API: http://127.0.0.1:8000; Web: http://127.0.0.1:5173", flush=True)
        while True:
            for name, process in zip(("API", "Web"), processes, strict=True):
                code = process.poll()
                if code is not None:
                    print(f"{name} exited unexpectedly (status {code}).", file=sys.stderr)
                    raise SystemExit(code if code > 0 else 1)
            for process in processes:
                try:
                    process.wait(timeout=0.4)
                except subprocess.TimeoutExpired:
                    pass
    except KeyboardInterrupt:
        pass
    except BaseException as error:
        failure = error
    finally:
        cleanup_failed = False
        for process in processes:
            try:
                cleanup_failed = not stop_dev_process(process) or cleanup_failed
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
        if job is not None:
            cleanup_failed = not job.terminate() or cleanup_failed
            job.close()
        if cleanup_failed:
            print("An owned development process could not be stopped.", file=sys.stderr)
    if cleanup_failed:
        raise SystemExit(1)
    if failure is not None:
        raise failure


def source_database_tunnel(settings=None) -> None:
    """Forward the local configured source-DB address to the deployment host."""
    import ipaddress

    if settings is None:
        from research_platform.core.config import Settings

        settings = Settings()
    source = settings.source_mysql
    if source is None:
        raise SystemExit("Source database is not configured")
    try:
        loopback = ipaddress.ip_address(source.host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise SystemExit("RP_SOURCE_MYSQL__HOST must be a loopback address for source-db")
    host = settings.source_ssh_host
    if not host:
        raise SystemExit("Set RP_SOURCE_SSH_HOST to the deployment host")
    identity = settings.source_ssh_identity
    if identity:
        identity_file = identity.expanduser()
        if not identity_file.is_file():
            raise SystemExit("RP_SOURCE_SSH_IDENTITY does not name a readable file")
    options = ["-N", "-o", "ExitOnForwardFailure=yes"]
    if identity:
        options.extend(["-i", str(identity_file)])
    options.extend(
        [
            "-L",
            f"{source.host}:{source.port}:127.0.0.1:{source.port}",
            f"root@{host}" if "@" not in host else host,
        ]
    )
    subprocess.run(["ssh", *options], check=True)


def database_config(target: str, connect: bool) -> None:
    from pydantic import ValidationError
    from pydantic_settings import SettingsError
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from research_platform.core.config import Settings
    from research_platform.core.database import make_application_engine, make_source_engine

    try:
        settings = Settings()
    except ValidationError as error:
        # ValidationError.errors() includes original inputs: never serialize it here.
        fields = [".".join(map(str, item["loc"])) or "database_roles" for item in error.errors()]
        raise SystemExit("Invalid database configuration fields: " + ", ".join(fields)) from None
    except SettingsError:
        raise SystemExit(
            "Invalid environment configuration encoding; inspect .env privately"
        ) from None
    profile = settings.database_mysql if target == "app" else settings.source_mysql
    summary = {"target": target, "configured": target == "app" or profile is not None}
    summary["driver"] = (
        "mysql+pymysql"
        if profile
        else (make_url(settings.application_url()).drivername if target == "app" else "disabled")
    )
    summary["tls"] = (
        profile.tls
        if profile
        else (
            None
            if target == "source"
            else ("not-applicable" if summary["driver"] == "sqlite" else "see-url")
        )
    )
    if target == "source":
        summary["source_permissions"] = "SELECT-only account required; not verified"
    print(json.dumps(summary), flush=True)
    if not connect:
        return
    if not summary["configured"]:
        raise SystemExit("SOURCE_NOT_CONFIGURED")
    engine = None
    try:
        engine = (
            make_application_engine(settings) if target == "app" else make_source_engine(settings)
        )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Database connectivity passed (SELECT 1 only; schema/permissions not verified)")
    except Exception:
        raise SystemExit(
            "Database connectivity failed; check credentials, network and TLS privately"
        ) from None
    finally:
        if engine is not None:
            engine.dispose()


# --- Open Design prototype access -------------------------------------------
# Open Design is a desktop app with no local HTTP/MCP surface, so the connection
# is read-only over its data directory. The prototype is a design reference, not
# a code source: this only reports structure and can copy the HTML out.

PROTOTYPE_MARKERS = ("stock-limit-up-analyzer", "stock-research-platform")
PROTOTYPE_ENTRY = "index.html"
PROTOTYPE_NAMESPACE = "release-stable-win"


def prototype_projects_root() -> Path:
    roaming = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
    return Path(roaming) / "Open Design" / "namespaces" / PROTOTYPE_NAMESPACE / "data" / "projects"


def prototype_find_project(root: Path) -> Path:
    if not root.is_dir():
        raise SystemExit(f"Open Design data directory not found: {root}; open the app once")
    matches = []
    for candidate in sorted(root.iterdir()):
        entry = candidate / PROTOTYPE_ENTRY
        if not candidate.is_dir() or not entry.is_file():
            continue
        for path in [entry, *sorted(candidate.glob("*.md"))]:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(marker in text for marker in PROTOTYPE_MARKERS):
                matches.append(candidate)
                break
    if not matches:
        raise SystemExit(f"No Open Design project mentions any of {PROTOTYPE_MARKERS}")
    if len(matches) > 1:
        listed = "\n".join(f"  {path}" for path in matches)
        raise SystemExit(f"Several prototype projects match; choose explicitly:\n{listed}")
    return matches[0]


def prototype_navigation(html: str) -> list[dict]:
    start = html.find("NAV = [")
    if start < 0:
        return []
    end = html.find("\n];", start)
    if end < 0:
        return []
    block = html[start : end + 3]
    groups = []
    for group in re.finditer(r'title:\s*"([^"]+)",\s*items:\s*\[(.*?)\]\s*\}', block, re.S):
        items = [
            {
                "id": match.group(1),
                "name": match.group(2),
                "implemented": "on: true" in match.group(3),
            }
            for match in re.finditer(
                r'\{\s*id:\s*"([^"]+)",\s*name:\s*"([^"]+)"([^}]*)\}', group.group(2)
            )
        ]
        groups.append({"title": group.group(1), "items": items})
    return groups


def prototype_views(html: str) -> list[str]:
    return sorted(set(re.findall(r"function\s+(render[A-Z][A-Za-z]*)", html)))


def prototype(action: str = "list", destination: str | None = None) -> None:
    """Report the connected Open Design prototype (or copy its HTML out)."""
    project = prototype_find_project(prototype_projects_root())
    entry = project / PROTOTYPE_ENTRY
    html = entry.read_text(encoding="utf-8", errors="ignore")
    if action == "copy":
        if not destination:
            raise SystemExit("prototype copy needs --to PATH")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry, target)
        print(f"copied prototype to {target} ({target.stat().st_size} bytes)")
        return
    navigation = prototype_navigation(html)
    views = prototype_views(html)
    if action == "shape":
        print(json.dumps({"navigation": navigation, "views": views}, ensure_ascii=False, indent=2))
        return
    print(f"project : {project.name}")
    print(f"entry   : {entry} ({entry.stat().st_size} bytes)")
    print(f"docs    : {len(list(project.glob('*.md')))}")
    implemented = 0
    total = 0
    for group in navigation:
        print(f"[{group['title']}]")
        for item in group["items"]:
            total += 1
            implemented += item["implemented"]
            mark = " " if item["implemented"] else "."
            print(f"  {mark} {item['id']:16s} {item['name']}")
    print(f"views   : {len(views)} render functions")
    print(f"entries : {implemented} implemented, {total - implemented} planned")


# --- brand icons ------------------------------------------------------------
# The favicon and app icons are generated from the same geometry the UI draws, so
# the browser tab, the shortcut and the in-app lockup cannot drift. Written with
# zlib and struct only, to avoid adding an image library to the runtime.


ICON_DIR = ROOT / "frontend" / "public"

# Brand colour (dark theme). The favicon is the one place a single colour must be
# hard-coded: it renders before any stylesheet, so it cannot read a CSS variable.
BRAND = (255, 106, 26)
WHITE = (255, 255, 255)

# The plinth glyph, expressed as the same path data the UI uses, flattened to
# polygons for a dependency-free rasteriser.
# Each course is a rhombus; the two lower ones are open bands drawn as thick lines,
# which matches how the mark reads at small sizes.
# Scaled to sit inside the tile with padding: a glyph that fills the whole square
# reads as a blob in a 16px browser tab, and the two lower courses merge together.
# Three equal courses. The top face is an outlined rhombus (not a solid fill) so
# all three read at the same weight; a filled top made the mark look like a stack
# of arrows instead of a plinth.
TOP = [(12.0, 4.2), (18.6, 8.1), (12.0, 12.0), (5.4, 8.1)]
GLYPH = [
    (TOP, "outline"),
    ([(5.4, 12.6), (12.0, 16.5), (18.6, 12.6)], "outline"),
    ([(5.4, 17.1), (12.0, 21.0), (18.6, 17.1)], "outline"),
]


def _coverage(px: float, py: float) -> tuple[float, float]:
    """Return (fill_inside, stroke_inside) for one sample point in 24×24 space."""
    filled = 0.0
    stroked = 0.0
    for points, mode in GLYPH:
        closed = mode == "outline"
        count = len(points)
        for index in range(count if closed else count - 1):
            a = points[index]
            b = points[(index + 1) % count]
            if _distance_to_segment(px, py, a, b) <= 0.85:
                stroked = 1.0
    return filled, stroked


def _point_in_polygon(px: float, py: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        if (y1 > py) != (y2 > py):
            cross = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < cross:
                inside = not inside
    return inside


def _distance_to_segment(
    px: float, py: float, a: tuple[float, float], b: tuple[float, float]
) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def render(size: int) -> list[list[tuple[int, int, int]]]:
    """Render the rounded-square mark at `size` px with 4×4 supersampling."""
    rows: list[list[tuple[int, int, int]]] = []
    scale = 24.0 / size
    samples = 4
    radius = 6.0 / 24.0  # corner radius as a fraction of the tile
    for y in range(size):
        row: list[tuple[int, int, int]] = []
        for x in range(size):
            fill_hit = 0
            glyph_hit = 0
            for sy in range(samples):
                for sx in range(samples):
                    px = (x + (sx + 0.5) / samples) * scale
                    py = (y + (sy + 0.5) / samples) * scale
                    # Rounded-square mask, in 0..1 normalised coordinates.
                    nx = (x + (sx + 0.5) / samples) / size
                    ny = (y + (sy + 0.5) / samples) / size
                    if not _inside_rounded_square(nx, ny, radius):
                        continue
                    fill_hit += 1
                    filled, stroked = _coverage(px, py)
                    if filled or stroked:
                        glyph_hit += 1
            total = samples * samples
            if fill_hit == 0:
                row.append((0, 0, 0, 0))  # type: ignore[arg-type]
                continue
            alpha = round(255 * fill_hit / total)
            glyph_ratio = glyph_hit / fill_hit
            red = round(BRAND[0] * (1 - glyph_ratio) + WHITE[0] * glyph_ratio)
            green = round(BRAND[1] * (1 - glyph_ratio) + WHITE[1] * glyph_ratio)
            blue = round(BRAND[2] * (1 - glyph_ratio) + WHITE[2] * glyph_ratio)
            row.append((red, green, blue, alpha))  # type: ignore[arg-type]
        rows.append(row)
    return rows


def _inside_rounded_square(nx: float, ny: float, radius: float) -> bool:
    cx = min(max(nx, radius), 1 - radius)
    cy = min(max(ny, radius), 1 - radius)
    if nx == cx and ny == cy:
        return True
    return ((nx - cx) ** 2 + (ny - cy) ** 2) ** 0.5 <= radius


def write_png(path: Path, size: int) -> None:
    pixels = render(size)
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0
        for pixel in row:
            raw.extend(pixel[:4] if len(pixel) == 4 else (*pixel, 255))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", header)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def write_svg(path: Path) -> None:
    """A vector favicon so high-DPI tabs and OS shortcuts stay crisp."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" '
        'aria-label="磐石 Quant Lab">'
        '<rect width="24" height="24" rx="6" fill="#ff6a1a"/>'
        '<g fill="none" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M12 4.6 19.4 8.4 12 12.2 4.6 8.4 12 4.6Z" fill="#ffffff" stroke="none"/>'
        '<path d="M4.6 13.1 12 17 19.4 13.1"/>'
        '<path d="M4.6 17.3 12 21.2 19.4 17.3"/>'
        "</g></svg>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg + "\n", encoding="utf-8")


def generate_brand_icons() -> None:
    write_svg(ICON_DIR / "favicon.svg")
    write_png(ICON_DIR / "favicon-32.png", 32)
    write_png(ICON_DIR / "apple-touch-icon.png", 180)
    write_png(ICON_DIR / "icon-192.png", 192)
    write_png(ICON_DIR / "icon-512.png", 512)
    print(f"brand icons written to {ICON_DIR}")


# --- identity administration ------------------------------------------------
# No admin web UI: for one or two users the operator issues an invitation code (or
# creates the account) from here. Only non-secret outcomes are printed; a new
# invitation code is shown exactly once because only its hash is stored.


def _identity_session():
    from sqlalchemy.orm import Session

    from research_platform.core.config import Settings
    from research_platform.core.database import make_application_engine

    settings = Settings()
    if settings.auth is None:
        raise SystemExit("Authentication is not configured: set RP_AUTH__SECRET (>=32 chars)")
    return Session(make_application_engine(settings)), settings


def _require_migrated(session) -> None:
    from sqlalchemy import text

    try:
        session.execute(text("SELECT id FROM user_account LIMIT 1"))
    except Exception:
        raise SystemExit(
            "Database is not migrated: run `uv run python tools/project.py migrate-local`"
        ) from None


def identity_admin(action: str, options: dict) -> None:
    from sqlalchemy import select, update

    from research_platform.modules.identity import invitations, service
    from research_platform.modules.identity.models import (
        UserAccount,
        UserCredential,
        UserSession,
        utc_now,
    )
    from research_platform.modules.identity.security import hash_password

    session, settings = _identity_session()
    try:
        _require_migrated(session)

        def account_for(email: str):
            account = session.scalar(
                select(UserAccount).where(UserAccount.email == service.normalize_email(email))
            )
            if account is None:
                raise SystemExit(f"No such account: {email}")
            return account

        def revoke_sessions(user_id: int) -> None:
            session.execute(
                update(UserSession)
                .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
                .values(revoked_at=utc_now())
            )

        if action == "user-create":
            email = service.normalize_email(options["email"])
            if session.scalar(select(UserAccount).where(UserAccount.email == email)):
                raise SystemExit(f"Account already exists: {email}")
            if len(options["password"]) < settings.auth.min_password_length:
                raise SystemExit("Password is shorter than RP_AUTH__MIN_PASSWORD_LENGTH")
            account = UserAccount(
                email=email,
                display_name=options.get("display_name", "").strip(),
                role=options.get("role", "user"),
            )
            session.add(account)
            session.flush()
            session.add(
                UserCredential(user_id=account.id, password_hash=hash_password(options["password"]))
            )
            session.commit()
            print(json.dumps({"created": email, "id": account.id, "role": account.role}))
        elif action == "user-list":
            rows = session.scalars(select(UserAccount).order_by(UserAccount.id)).all()
            if not rows:
                print("No accounts yet.")
            else:
                print(f"{'id':>4}  {'email':32}  {'role':6}  {'active':6}  last signed in")
                for row in rows:
                    last = (
                        row.last_signed_in_at.isoformat(timespec="seconds")
                        if row.last_signed_in_at
                        else "-"
                    )
                    print(
                        f"{row.id:>4}  {row.email:32}  {row.role:6}  {str(row.is_active):6}  {last}"
                    )
        elif action == "user-disable":
            account = account_for(options["email"])
            account.is_active = False
            revoke_sessions(account.id)
            session.commit()
            print(json.dumps({"disabled": account.email, "sessions_revoked": True}))
        elif action == "user-reset-password":
            account = account_for(options["email"])
            credential = session.scalar(
                select(UserCredential).where(UserCredential.user_id == account.id)
            )
            if credential is None:
                raise SystemExit(f"No credential row for {account.email}")
            if len(options["password"]) < settings.auth.min_password_length:
                raise SystemExit("Password is shorter than RP_AUTH__MIN_PASSWORD_LENGTH")
            credential.password_hash = hash_password(options["password"])
            credential.password_updated_at = utc_now()
            credential.failed_attempts = 0
            credential.locked_until = None
            revoke_sessions(account.id)
            session.commit()
            print(json.dumps({"password_reset": account.email, "sessions_revoked": True}))
        elif action == "invite-create":
            code, row = invitations.issue(
                session,
                settings.auth,
                label=options.get("label", ""),
                ttl_hours=options.get("ttl_hours"),
            )
            print(
                json.dumps(
                    {
                        "code": code,
                        "id": row.id,
                        "label": row.label,
                        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    }
                )
            )
            print("上面是唯一一次显示明文邀请码；数据库只保存哈希。")
        elif action == "invite-list":
            rows = invitations.list_codes(session)
            if not rows:
                print("No invitation codes.")
            else:
                now = utc_now()
                print(f"{'id':36}  {'label':20}  {'state':12}  created")
                for row in rows:
                    state = "usable" if invitations.is_usable(row, now) else "spent/expired"
                    if row.revoked_at is not None:
                        state = "revoked"
                    print(
                        f"{row.id:36}  {row.label[:20]:20}  {state:12}  "
                        f"{row.created_at.isoformat(timespec='seconds')}"
                    )
        elif action == "invite-revoke":
            invitations.revoke(session, options["code_id"])
            print(json.dumps({"revoked": options["code_id"]}))
        else:
            raise SystemExit(f"unknown identity action: {action}")
    except Exception as error:  # noqa: BLE001 - surface the code, never a traceback
        from research_platform.core.errors import DomainError

        if isinstance(error, DomainError):
            raise SystemExit(f"{error.code}: {error.message}") from None
        raise
    finally:
        session.close()


def market_check() -> None:
    """Read-only probe of the public market sources; never writes, never prints secrets.

    Reports what actually happened, including a degraded auction: an empty curve
    with a recovered 09:25 trade is "degraded", not "ok" and not "empty".
    """
    from research_platform.core.config import Settings
    from research_platform.core.errors import DomainError
    from research_platform.core.upstream import UpstreamClient
    from research_platform.modules.market.service import MarketService

    settings = Settings()
    client = UpstreamClient(settings)
    service = MarketService(settings, client)
    summary: dict[str, str] = {}
    try:
        for probe, call in (
            ("quote", lambda: service.quote("600519")),
            ("intraday", lambda: service.intraday("600519", "m1", 5)),
            ("auction", lambda: service.auction("600519")),
            ("daily", lambda: service.daily("600519", None, None)),
        ):
            try:
                result = call()
                if probe == "quote":
                    summary[probe] = f"ok (price={result.price})"
                elif probe == "auction":
                    if result.degraded:
                        summary[probe] = (
                            f"degraded (provider={result.provider}, "
                            f"snapshots={len(result.snapshots)}, "
                            f"matched={result.matched_price})"
                        )
                    else:
                        summary[probe] = f"ok ({len(result.snapshots)} snapshots)"
                else:
                    summary[probe] = f"ok ({result.total} bars)"
            except DomainError as error:
                summary[probe] = f"unavailable ({error.code})"
    finally:
        client.close()
    summary["tushare_configured"] = str(settings.tushare is not None).lower()
    summary["upstream_enabled"] = str(settings.upstream.enabled).lower()
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def market_state_description(
    action: str,
    *,
    trade_date: str | None = None,
    start: str | None = None,
    end: str | None = None,
    output: str | None = None,
) -> None:
    """Describe or scan the configured frozen market-state delivery."""
    from research_platform.core.config import Settings
    from research_platform.core.errors import DomainError
    from research_platform.modules.market.state_description import (
        MarketStateDescriptionService,
    )
    from research_platform.modules.market.state_source import FrozenMarketStateSource

    settings = Settings()
    if settings.market_state is None:
        raise SystemExit("RP_MARKET_STATE__ROOT is not configured")
    config = settings.market_state
    service = MarketStateDescriptionService(FrozenMarketStateSource(config.root), config)
    try:
        if action == "describe":
            payload = service.describe(
                date.fromisoformat(trade_date) if trade_date else None
            ).model_dump(mode="json")
        elif action == "scan":
            payload = service.scan(
                date.fromisoformat(start) if start else None,
                date.fromisoformat(end) if end else None,
            )
        else:
            raise SystemExit(f"unknown market-state action: {action}")
    except DomainError as error:
        raise SystemExit(f"{error.code}: {error.message}") from None
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        target = Path(output)
        if not target.is_absolute():
            target = ROOT / target
        target = target.resolve()
        if not target.is_relative_to(SCRATCH.resolve()):
            raise SystemExit("market-state output must be inside .scratch")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def review_counts(action: str, *, days: int | None = None, as_of: str | None = None) -> None:
    """Refresh or inspect the platform's derived daily limit counts."""
    from sqlalchemy.orm import sessionmaker

    from research_platform.core.config import Settings
    from research_platform.core.database import make_application_engine, make_source_engine
    from research_platform.core.errors import DomainError
    from research_platform.modules.market.legacy_review_source import LegacyMarketReviewSource
    from research_platform.modules.market.market_time import exchange_now
    from research_platform.modules.market.review_counts_refresh import ReviewCountsService
    from research_platform.modules.market.review_counts_store import SqlReviewCountsStore

    settings = Settings()
    if settings.source_mysql is None:
        raise SystemExit("Source database is not configured")
    app_engine = make_application_engine(settings)
    source_engine = make_source_engine(settings)
    sessions = sessionmaker(app_engine, expire_on_commit=False)
    service = ReviewCountsService(
        LegacyMarketReviewSource(source_engine),
        SqlReviewCountsStore(sessions),
        settings.review_counts,
        lookback_days=settings.review.lookback_days,
    )
    try:
        if action == "refresh":
            result = service.refresh(
                as_of=date.fromisoformat(as_of) if as_of else None,
                days=days,
            )
            payload = {
                "refreshed": [item.isoformat() for item in result.trading_days],
                "skipped": [item.isoformat() for item in result.skipped_days],
                "latest_trading_day": result.latest_trading_day.isoformat()
                if result.latest_trading_day
                else None,
                "empty": result.empty,
            }
        elif action == "status":
            latest = service.store.latest_trading_day()
            eligible = service.latest_eligible_day(exchange_now())
            payload = {
                "stored_latest_trading_day": latest.isoformat() if latest else None,
                "latest_eligible_source_trading_day": eligible.isoformat() if eligible else None,
                "backfill_days": settings.review_counts.backfill_days,
                "enabled": settings.review_counts.enabled,
            }
        else:
            raise SystemExit(f"unknown review-counts action: {action}")
    except DomainError as error:
        raise SystemExit(f"{error.code}: {error.message}") from None
    finally:
        source_engine.dispose()
        app_engine.dispose()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task",
        choices=[
            "check",
            "hygiene",
            "contract",
            "migrate-local",
            "dev",
            "source-db",
            "worker",
            "db-config",
            "db-check",
            "market-check",
            "market-state",
            "review-counts",
            "prototype",
            "identity",
            "icons",
        ],
    )
    parser.add_argument("--target", choices=["app", "source"], default="app")
    parser.add_argument(
        "--action",
        choices=["list", "shape", "copy"],
        default="list",
        help="prototype: list navigation, dump shape JSON, or copy the HTML",
    )
    parser.add_argument("--to", metavar="PATH", help="prototype copy: destination path")
    parser.add_argument(
        "--market-state-action",
        choices=["describe", "scan"],
        default="describe",
        help="market-state: emit one date or scan label distribution",
    )
    parser.add_argument("--date", help="market-state describe: YYYY-MM-DD")
    parser.add_argument(
        "--review-counts-action",
        dest="review_counts_action",
        choices=["refresh", "status"],
        default="refresh",
        help="review-counts: backfill/refresh or inspect the derived daily counts",
    )
    parser.add_argument("--days", type=int, help="review-counts refresh: trading days to recompute")
    parser.add_argument("--as-of", help="review-counts refresh: YYYY-MM-DD upper bound")
    parser.add_argument("--start", help="market-state scan: YYYY-MM-DD")
    parser.add_argument("--end", help="market-state scan: YYYY-MM-DD")
    parser.add_argument("--output", help="market-state: optional .scratch JSON path")
    parser.add_argument(
        "--identity-action",
        dest="identity_action",
        choices=[
            "user-create",
            "user-list",
            "user-disable",
            "user-reset-password",
            "invite-create",
            "invite-list",
            "invite-revoke",
        ],
        help="identity administration action",
    )
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--display-name", default="")
    parser.add_argument("--role", default="user", choices=["user", "admin"])
    parser.add_argument("--label", default="")
    parser.add_argument("--ttl-hours", type=int)
    parser.add_argument("--code-id")
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.task in ("db-config", "db-check"):
        database_config(args.target, connect=args.task == "db-check")
    elif args.task == "hygiene":
        hygiene()
    elif args.task == "contract":
        contract()
    elif args.task == "migrate-local":
        migrate()
    elif args.task == "dev":
        dev()
    elif args.task == "source-db":
        source_database_tunnel()
    elif args.task == "worker":
        run(sys.executable, "-m", "research_platform.modules.execution.worker")
    elif args.task == "market-check":
        market_check()
    elif args.task == "market-state":
        market_state_description(
            args.market_state_action,
            trade_date=args.date,
            start=args.start,
            end=args.end,
            output=args.output,
        )
    elif args.task == "review-counts":
        review_counts(
            args.review_counts_action,
            days=args.days,
            as_of=args.as_of,
        )
    elif args.task == "prototype":
        prototype(args.action, args.to)
    elif args.task == "icons":
        generate_brand_icons()
    elif args.task == "identity":
        if not args.identity_action:
            raise SystemExit("identity needs --identity-action; run --help")
        identity_admin(
            args.identity_action,
            {
                "email": args.email,
                "password": args.password,
                "display_name": args.display_name,
                "role": args.role,
                "label": args.label,
                "ttl_hours": args.ttl_hours,
                "code_id": args.code_id,
            },
        )
    else:
        hygiene()
        run("ruff", "check", "backend", "tools")
        run("ruff", "format", "--check", "backend", "tools")
        run("pytest")
        contract(check=True)
        frontend("run", "lint")
        frontend("run", "format:check")
        frontend("run", "test")
        frontend("run", "build")


if __name__ == "__main__":
    main()
