"""The only general-purpose project task entry point. Run from any directory."""

import argparse
import json
import os
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
    if not committed.exists() or generated.read_text() != committed.read_text():
        raise SystemExit("API contract drift: run `uv run python tools/project.py contract`")


def migrate() -> None:
    from research_platform.core.config import Settings

    settings = Settings()
    url = settings.database_url.get_secret_value()
    if settings.environment == "production" or not url.startswith("sqlite:///"):
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task", choices=["check", "hygiene", "contract", "migrate-local", "dev", "worker"]
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.task == "hygiene":
        hygiene()
    elif args.task == "contract":
        contract()
    elif args.task == "migrate-local":
        migrate()
    elif args.task == "dev":
        dev()
    elif args.task == "worker":
        run(sys.executable, "-m", "research_platform.modules.execution.worker")
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
