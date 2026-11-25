"""Verify all relative Markdown links and backticked repository paths exist on disk."""

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {".git", ".venv", "__pycache__", "scratch", "var"}

MD_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BACKTICK_PATTERN = re.compile(r"`([^`\n]+)`")

REPO_ROOT_PREFIXES = (
    "medicare/",
    "ui/",
    "data/",
    "var/",
    "config/",
    "docs/",
    "evals/",
    "tests/",
    "scripts/",
    "Makefile",
    "README.md",
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
)


def check_docs_links() -> list[str]:
    errors = []
    md_files = []

    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f.endswith(".md"):
                md_files.append(Path(root) / f)

    for md_path in md_files:
        rel_md = md_path.relative_to(REPO_ROOT)
        text = md_path.read_text(encoding="utf-8", errors="ignore")

        # 1. Check relative Markdown links
        for match in MD_LINK_PATTERN.finditer(text):
            target = match.group(2).strip()

            # Ignore external URLs and purely internal anchors
            if (
                target.startswith("http://")
                or target.startswith("https://")
                or target.startswith("mailto:")
                or target.startswith("#")
                or target == ""
            ):
                continue

            # Strip anchor if present
            file_target = target.split("#")[0]
            if not file_target:
                continue

            resolved = (md_path.parent / file_target).resolve()
            if not resolved.exists():
                errors.append(
                    f"Broken markdown link in {rel_md}: [{match.group(1)}]({target}) -> {file_target} does not exist"
                )

        # 2. Check backticked repository paths
        for match in BACKTICK_PATTERN.finditer(text):
            candidate = match.group(1).strip()
            # Check if this matches a known repo prefix
            if any(candidate.startswith(pref) for pref in REPO_ROOT_PREFIXES):
                # Clean up any trailing punctuation or wildcards
                clean_cand = candidate.split()[0].rstrip(",;.:")
                if "*" in clean_cand or "<" in clean_cand or ">" in clean_cand:
                    continue
                path_to_check = REPO_ROOT / clean_cand
                if not path_to_check.exists() and not str(rel_md).startswith("docs/decisions/"):
                    errors.append(
                        f"Broken backticked path in {rel_md}: `{candidate}` does not exist on disk"
                    )

    return errors


def main() -> None:
    print("Checking documentation links and backticked repo paths...")
    errors = check_docs_links()
    if errors:
        print(f"\n❌ Docs link verification FAILED with {len(errors)} broken references:\n")
        for err in errors:
            print(f"  • {err}")
        sys.exit(1)
    else:
        print("\n✅ Docs link verification PASSED: All Markdown links and repo paths exist.")
        sys.exit(0)


if __name__ == "__main__":
    main()
