import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/research_platform"


def test_module_imports_and_business_logic_do_not_leak_across_seams():
    violations = []
    for source in (ROOT / "modules").rglob("*.py"):
        module = source.relative_to(ROOT / "modules").parts[0]
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module
                if source.name == "service.py" and imported.startswith("fastapi"):
                    violations.append(f"{source.name}: business logic imports HTTP framework")
                if imported.startswith("research_platform.modules."):
                    target = imported.split(".")[2]
                    permitted_identity_seam = (
                        source.name == "router.py"
                        and imported == "research_platform.modules.identity.dependencies"
                    )
                    if target != module and not permitted_identity_seam:
                        violations.append(f"{source}: cross-module import {imported}")
    assert not violations, violations


def test_core_has_no_business_module_imports():
    for source in (ROOT / "core").glob("*.py"):
        assert "research_platform.modules" not in source.read_text(encoding="utf-8")
