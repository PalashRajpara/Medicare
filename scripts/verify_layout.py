"""Verify repository layout, layering constraints, clean imports, and path hygiene."""

import ast
import importlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_ROOT_ENTRIES = {
    "README.md",
    "Makefile",
    "pyproject.toml",
    "uv.lock",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    ".env",
    "medicare",
    "ui",
    "config",
    "data",
    "var",
    "tests",
    "evals",
    "scripts",
    "docs",
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".agents",
    ".claude",
    ".DS_Store",
    ".streamlit",
}

IGNORED_PATHS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "scratch",
    ".claude",
    ".DS_Store",
    ".streamlit",
    "var",
}


def verify_root_entries() -> list[str]:
    """Ensure root contains only target structure files and directories."""
    errors = []
    actual_entries = set(os.listdir(REPO_ROOT))
    unexpected = actual_entries - ALLOWED_ROOT_ENTRIES
    if unexpected:
        errors.append(f"Unexpected entries in repository root: {sorted(unexpected)}")
    if (REPO_ROOT / "scratch").exists():
        errors.append("scratch/ directory still exists in repository root.")
    return errors


def verify_no_db_outside_var() -> list[str]:
    """Ensure no database files exist outside var/."""
    errors = []
    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip virtualenv and git
        if any(ign in root for ign in [".git", ".venv", "scratch"]):
            continue
        rel_root = Path(root).relative_to(REPO_ROOT)
        if str(rel_root).startswith("var"):
            continue
        for f in files:
            if f.endswith((".db", ".sqlite", ".sqlite3")) and not f.endswith("checkpoint.db"):
                errors.append(f"Database file found outside var/: {rel_root / f}")
    return errors


def verify_clean_imports() -> list[str]:
    """Verify all modules under medicare and ui can be imported cleanly."""
    errors = []
    sys_path_root = str(REPO_ROOT)
    if sys_path_root not in sys.path:
        sys.path.insert(0, sys_path_root)

    packages = ["medicare", "ui"]
    for pkg in packages:
        pkg_dir = REPO_ROOT / pkg
        for root, _, files in os.walk(pkg_dir):
            if "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(REPO_ROOT)
                    mod_parts = list(rel_p.parts[:-1]) + [rel_p.stem]
                    if mod_parts[-1] == "__init__":
                        mod_parts = mod_parts[:-1]
                    if not mod_parts:
                        continue
                    mod_name = ".".join(mod_parts)
                    try:
                        importlib.import_module(mod_name)
                    except Exception as e:
                        errors.append(f"Failed to import {mod_name} ({rel_p}): {e}")
    return errors


def verify_layering_rules() -> list[str]:
    """Verify architectural import boundaries using AST parsing.

    Rules:
    - api/ imports from agents/, security/, storage/, domain/, config (no business logic)
    - agents/ may import medicare/, rag/, tools/, providers/, runtime/
    - rag/, tools/, providers/, security/, runtime/, storage/, domain/ must NOT import agents/, api/, or medicare/
    - ui/ must NOT import medicare at all
    """
    errors = []
    lower_layers = {
        "medicare/rag",
        "medicare/tools",
        "medicare/providers",
        "medicare/security",
        "medicare/runtime",
        "medicare/storage",
        "medicare/domain",
    }

    for root, _, files in os.walk(REPO_ROOT):
        if any(ign in root for ign in [".git", ".venv", "__pycache__", "tests", "scratch"]):
            continue

        for f in files:
            if not f.endswith(".py"):
                continue
            file_path = Path(root) / f
            rel_file = str(file_path.relative_to(REPO_ROOT)).replace("\\", "/")

            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
            except Exception as e:
                errors.append(f"Failed to parse AST for {rel_file}: {e}")
                continue

            for node in ast.walk(tree):
                imported_mods = []
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_mods.append(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_mods.append(node.module)

                for mod in imported_mods:
                    # Rule 1: ui/ must not import medicare
                    if rel_file.startswith("ui/") and mod.startswith("medicare"):
                        errors.append(
                            f"Layering violation: ui/ file {rel_file} imports backend {mod}"
                        )

                    # Rule 2: lower layers must not import agents, api, or medicare
                    is_lower = any(rel_file.startswith(l_dir) for l_dir in lower_layers)
                    if is_lower and (
                        mod.startswith("medicare.agents")
                        or mod.startswith("medicare.api")
                        or mod.startswith("medicare.medicare")
                    ):
                        errors.append(
                            f"Layering violation: lower layer {rel_file} imports upper layer {mod}"
                        )

                    # Rule 3: api/ must not import medicare directly (except routes/medicare or schema)
                    if rel_file.startswith("medicare/api/") and mod.startswith(
                        "medicare.medicare.graph"
                    ):
                        errors.append(
                            f"Layering violation: API layer {rel_file} imports internal graph {mod}"
                        )
    return errors


def verify_no_old_paths() -> list[str]:
    """Ensure no old paths or module names remain outside docs/decisions."""
    errors = []
    old_patterns = [
        "nexus_agent",
        "nexus-agent",
        "NexusAgent",
        "nexus-setup",
        "nexus-evals",
        "routes_medicare",
        "routes_info",
        "routes_stream",
        "routes_invoke",
        "routes_agui",
        "routes_feedback",
        "routes_threads",
        "routes_documents",
        "medicare_data.db",
        "data/hospitals.db",
        "data/manifest.db",
        "data/chroma",
    ]

    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [
            d
            for d in dirs
            if d
            not in {".git", ".venv", "__pycache__", "scratch", "scripts", "var", "node_modules"}
        ]
        if any(
            ign in root
            for ign in [
                ".git",
                ".venv",
                "__pycache__",
                "docs/decisions",
                "scratch",
                "scripts",
                "var",
            ]
        ):
            continue
        for f in files:
            if f.endswith((".py", ".md", ".yaml", ".yml", ".toml", "Dockerfile")):
                file_p = Path(root) / f
                rel_f = str(file_p.relative_to(REPO_ROOT))
                if rel_f.startswith(("var/", "var\\")):
                    continue
                try:
                    text = file_p.read_text(encoding="utf-8", errors="ignore")
                    for pat in old_patterns:
                        if pat in text:
                            errors.append(f"Reference to obsolete path '{pat}' in {rel_f}")
                except Exception:
                    pass
    return errors


def main() -> None:
    all_errors = []

    print("Verifying root entries...")
    all_errors.extend(verify_root_entries())

    print("Verifying database isolation (all .db in var/)...")
    all_errors.extend(verify_no_db_outside_var())

    print("Verifying clean imports across packages...")
    all_errors.extend(verify_clean_imports())

    print("Verifying architectural layering rules with AST...")
    all_errors.extend(verify_layering_rules())

    print("Verifying no obsolete paths remain...")
    all_errors.extend(verify_no_old_paths())

    if all_errors:
        print(f"\n❌ Layout verification FAILED with {len(all_errors)} errors:\n")
        for err in all_errors:
            print(f"  • {err}")
        sys.exit(1)
    else:
        print("\n✅ Layout verification PASSED: Repository structure matches target specification.")
        sys.exit(0)


if __name__ == "__main__":
    main()
