"""Every local module a copied file imports is copied too.

The PAXminer images list files by name. A new import that is not in that list
is a ModuleNotFoundError after deploy, which is what happened to region_data.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAX = ROOT / "PAXminer"


def copy_sources(dockerfile: str) -> list[str]:
    sources = []
    for raw in dockerfile.splitlines():
        line = raw.strip()
        if not line.startswith("COPY PAXminer/"):
            continue
        src = line.split()[1].removeprefix("PAXminer/").rstrip("/")
        sources.append(src)
    return sources


def covered(rel: str, sources: list[str]) -> bool:
    for src in sources:
        if rel == src or rel.startswith(src + "/"):
            return True
    return False


def local_paths(module: str) -> list[str]:
    parts = module.split(".")
    found = []
    file_path = PAX.joinpath(*parts).with_suffix(".py")
    init_path = PAX.joinpath(*parts, "__init__.py")
    if file_path.is_file():
        found.append(file_path.relative_to(PAX).as_posix())
    if init_path.is_file():
        found.append(init_path.relative_to(PAX).as_posix())
    return found


def _package_of(rel: str) -> list[str]:
    parts = Path(rel).with_suffix("").parts
    if Path(rel).name == "__init__.py":
        return list(Path(rel).parent.parts)
    return list(parts[:-1])


def imported_modules(rel: str, tree: ast.AST) -> set[str]:
    modules = set()
    package = _package_of(rel)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level:
            base = package[: len(package) - (node.level - 1)]
            if node.module:
                base.append(node.module)
            if base:
                modules.add(".".join(base))
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def missing_imports(dockerfile: str) -> list[str]:
    sources = copy_sources(dockerfile)
    copied_py = []
    for path in PAX.rglob("*.py"):
        rel = path.relative_to(PAX).as_posix()
        if covered(rel, sources):
            copied_py.append(rel)
    missing = []
    for rel in copied_py:
        tree = ast.parse((PAX / rel).read_text(encoding="utf-8"))
        for module in imported_modules(rel, tree):
            for target in local_paths(module):
                if not covered(target, sources):
                    missing.append(f"{rel} imports {module} ({target})")
    return sorted(set(missing))


def test_dockerfiles_copy_every_local_import():
    for name in ("Dockerfile", "Dockerfile.slack"):
        missing = missing_imports((PAX / name).read_text(encoding="utf-8"))
        assert missing == [], f"{name} is missing copies:\n" + "\n".join(missing)


def test_omitting_region_data_is_reported():
    text = (PAX / "Dockerfile").read_text(encoding="utf-8")
    text = text.replace("COPY PAXminer/region_data.py ./\n", "")
    missing = missing_imports(text)
    assert any("region_data.py" in item for item in missing)
