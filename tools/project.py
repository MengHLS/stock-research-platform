"""The only general-purpose project task entry point. Run from any directory."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".scratch"
DOCS = {
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
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


def dev() -> None:
    SCRATCH.mkdir(exist_ok=True)
    pnpm = shutil.which("pnpm")
    if not pnpm:
        raise SystemExit("pnpm is required; install the packageManager version from package.json")
    processes = [
        subprocess.Popen(
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
        ),
        subprocess.Popen([pnpm, "dev"], cwd=ROOT / "frontend"),
    ]
    try:
        while all(p.poll() is None for p in processes):
            for process in processes:
                try:
                    process.wait(timeout=0.4)
                except subprocess.TimeoutExpired:
                    pass
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False)
                else:
                    process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


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
            "worker",
            "db-config",
            "db-check",
            "market-check",
            "prototype",
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
    elif args.task == "worker":
        run(sys.executable, "-m", "research_platform.modules.execution.worker")
    elif args.task == "market-check":
        market_check()
    elif args.task == "prototype":
        prototype(args.action, args.to)
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
