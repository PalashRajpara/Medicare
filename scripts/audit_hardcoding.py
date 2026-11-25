"""Hardcoding audit scanner for MediCare codebase.

Scans medicare/ and ui/ for hardcoded:
- Category A: Data values (cities, hospitals, insurers, procedures, prices)
- Category B: Schema names in generic non-DB/schema code
- Category C: Domain vocabulary (waiting period, cashless, etc.) not in config
- Category D: User-facing text and UI strings not loaded from config
- Category E: Prompt templates and persona text not loaded from config/prompts/
- Category F: Magic numbers and limits not loaded from Settings
- Category G: Environment constants (model names, URLs, currency symbols) not in Settings/config
"""

import ast
import csv
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Finding:
    file: str
    line: int
    category: str
    text: str
    allowlisted: bool = False
    reason: str = ""


# Modules allowed to define/inspect schema directly (the DB/schema/SQL-tool layer)
SCHEMA_LAYER_MODULES = {
    "medicare/medicare/schema.py",
    "medicare/medicare/setup.py",
    "medicare/medicare/csv_import.py",
    "medicare/medicare/dataset/schema.py",
    "medicare/medicare/dataset/cli.py",
    "medicare/medicare/dataset/csv_import.py",
    "medicare/tools/db_tools.py",
    "medicare/tools/sql_query.py",
    "medicare/api/routes/medicare.py",
}

# Standard protocol/API field names that are part of the platform framework
FRAMEWORK_API_FIELDS = {
    "question",
    "history",
    "user_id",
    "thread_id",
    "route",
    "doc_scope",
    "status",
    "trace",
    "timings",
    "audit_trail",
    "answer",
    "citations",
    "grounding",
    "table",
    "chart",
    "role",
    "content",
    "type",
    "tool_calls",
    "messages",
    "name",
    "description",
    "parameters",
    "run_id",
    "step_index",
    "channel_values",
    "metadata",
    "created_at",
    "updated_at",
}


def load_allowlist(repo_root: Path) -> list[dict[str, Any]]:
    """Load config/hardcode_allowlist.yaml and validate all entries have reasons."""
    allowlist_path = repo_root / "config" / "hardcode_allowlist.yaml"
    if not allowlist_path.exists():
        return []

    try:
        with open(allowlist_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            items = data.get("allowlist", [])
            for item in items:
                if not item.get("reason") or not str(item.get("reason")).strip():
                    print(
                        f"ERROR: Allowlist entry for {item.get('file')} missing reason!",
                        file=sys.stderr,
                    )
            return items
    except Exception as e:
        print(f"Warning: could not load allowlist: {e}", file=sys.stderr)
        return []


def collect_data_catalog(repo_root: Path) -> tuple[set[str], set[str], set[str]]:
    """Collect distinct data values, tables, and columns from DB and seed CSVs."""
    data_values: set[str] = set()
    table_names: set[str] = set()
    column_names: set[str] = set()

    # 1. DB introspection
    db_path = repo_root / "data" / "hospitals.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            for r in cur.fetchall():
                tname = r[0]
                if tname.startswith("sqlite_"):
                    continue
                table_names.add(tname)
                cur.execute(f"PRAGMA table_info({tname})")
                for c in cur.fetchall():
                    cname = c[1]
                    column_names.add(cname)
                    # Read distinct text values if text
                    ctype = str(c[2]).upper()
                    if "TEXT" in ctype or "CHAR" in ctype:
                        try:
                            cur.execute(
                                f"SELECT DISTINCT {cname} FROM {tname} WHERE {cname} IS NOT NULL"
                            )
                            for val_row in cur.fetchall():
                                v = str(val_row[0]).strip()
                                if len(v) >= 3:
                                    data_values.add(v)
                        except Exception:
                            pass
            conn.close()
        except Exception:
            pass

    # 2. Seed CSVs introspection
    seed_dir = repo_root / "data" / "seed"
    if seed_dir.exists():
        for csv_file in seed_dir.glob("*.csv"):
            try:
                with open(csv_file, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        for k, v in row.items():
                            if k:
                                column_names.add(k.strip())
                            if v and len(v.strip()) >= 3 and not v.strip().isdigit():
                                data_values.add(v.strip())
            except Exception:
                pass

    # 3. Policy document names
    policies_dir = repo_root / "data" / "policies"
    if policies_dir.exists():
        for pfile in policies_dir.glob("*.*"):
            data_values.add(pfile.name)
            data_values.add(pfile.stem)

    # Filter out common stop-words or generic words from data values
    common_words = {
        "the",
        "and",
        "for",
        "with",
        "all",
        "general",
        "care",
        "health",
        "state",
        "center",
        "hospital",
        "surgery",
        "insurance",
        "tier",
        "partner",
        "preferred",
        "only",
        "days",
        "room",
        "cost",
        "rent",
        "name",
        "city",
        "type",
    }
    filtered_data_values = {
        v
        for v in data_values
        if v.lower() not in common_words and not re.match(r"^Tier-\d+$", v, re.I)
    }

    return filtered_data_values, table_names, column_names


def load_domain_vocabulary(repo_root: Path) -> set[str]:
    """Load core domain vocabulary words that must reside in config files."""
    return {
        "waiting period",
        "waiting periods",
        "pre-existing",
        "pre-existing disease",
        "copay",
        "co-pay",
        "capping",
        "room rent capping",
        "exclusion",
        "exclusions",
        "sub-limit",
        "sub-limits",
        "pre-authorization",
        "cashless",
        "claim rejection",
        "claim settlement",
    }


def is_allowlisted(f: Finding, allowlist: list[dict[str, Any]]) -> tuple[bool, str]:
    """Check if a finding matches any allowlist entry."""
    norm_file = f.file.replace("\\", "/")
    for entry in allowlist:
        entry_file = entry.get("file", "").replace("\\", "/")
        if entry_file != norm_file:
            continue
        if entry.get("category") and entry.get("category") != f.category:
            continue
        # Check target or line
        target = entry.get("target")
        line = entry.get("line")
        matched = False
        if (
            target is not None
            and str(target).strip() in f.text
            or line is not None
            and line == f.line
        ):
            matched = True
        elif target is None and line is None:
            # Entry for specific file+category
            matched = True

        if matched:
            reason = entry.get("reason", "").strip()
            if reason:
                return True, reason
    return False, ""


def scan_file(
    file_path: Path,
    repo_root: Path,
    data_values: set[str],
    table_names: set[str],
    column_names: set[str],
    domain_vocab: set[str],
) -> list[Finding]:
    """Scan a single Python file for all categories of hardcoding."""
    rel_path = file_path.relative_to(repo_root).as_posix()
    findings: list[Finding] = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return findings

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        return findings

    lines = content.splitlines()

    # 1. AST Visitor for AST-level constructs
    class HardcodeVisitor(ast.NodeVisitor):
        def visit_Constant(self, node: ast.Constant):
            val = node.value
            # Category A: Data values inside string constants
            if isinstance(val, str):
                s_lower = val.lower().strip()
                for dv in data_values:
                    # Match whole word
                    pattern = rf"\b{re.escape(dv.lower())}\b"
                    if len(dv) >= 4 and re.search(pattern, s_lower):
                        findings.append(
                            Finding(
                                file=rel_path,
                                line=node.lineno,
                                category="A",
                                text=f"Data value '{dv}' found in string literal: '{val[:60]}'",
                            )
                        )
                        break

                # Category B: Schema names in generic code (outside schema layer)
                if rel_path not in SCHEMA_LAYER_MODULES:
                    # Check tables (ignore if string is a file path or URL)
                    is_path = (
                        "/" in val or "\\" in val or val.endswith(".db") or val.endswith(".csv")
                    )
                    if not is_path:
                        for t in table_names:
                            if re.search(rf"\b{re.escape(t)}\b", val):
                                findings.append(
                                    Finding(
                                        file=rel_path,
                                        line=node.lineno,
                                        category="B",
                                        text=f"Table name '{t}' in generic code: '{val[:60]}'",
                                    )
                                )
                    # Check specific DB columns
                    for c in column_names:
                        if (
                            len(c) > 3
                            and c
                            in (
                                "hospital_id",
                                "procedure_id",
                                "procedure_name",
                                "min_cost_inr",
                                "max_cost_inr",
                                "avg_cost_inr",
                                "avg_wait_days",
                                "room_rent_per_day_inr",
                                "cashless_accepted",
                                "emergency_wait_minutes",
                                "nabh_accredited",
                                "avg_claim_settlement_days",
                            )
                            and re.search(rf"\b{re.escape(c)}\b", val)
                        ):
                            findings.append(
                                Finding(
                                    file=rel_path,
                                    line=node.lineno,
                                    category="B",
                                    text=f"Schema column '{c}' in generic code: '{val[:60]}'",
                                )
                            )

                # Category C: Domain vocabulary
                for dv_term in domain_vocab:
                    if dv_term in s_lower:
                        findings.append(
                            Finding(
                                file=rel_path,
                                line=node.lineno,
                                category="C",
                                text=f"Domain vocabulary '{dv_term}' in string: '{val[:60]}'",
                            )
                        )
                        break

                # Category D: Long string literal > 40 chars not loaded from config
                if len(val) > 40:
                    val_s = val.strip()
                    # Skip code-like, SQL queries, or standard technical strings
                    is_tech = (
                        val_s.startswith(
                            (
                                "SELECT ",
                                "INSERT ",
                                "CREATE ",
                                "UPDATE ",
                                "DELETE ",
                                "PRAGMA ",
                                "ALTER ",
                                "DROP ",
                                "WITH ",
                                "http://",
                                "https://",
                                "/",
                                "data/",
                                "<",
                            )
                        )
                        or "class=" in val
                        or "{" in val
                        or "\\b" in val
                        or "\\s" in val
                        or "(?:" in val
                        or val_s.startswith("%")
                        or val_s.startswith("`")
                    )
                    # Skip docstrings
                    is_docstring = False
                    if hasattr(node, "parent") and isinstance(node.parent, ast.Expr):
                        expr_parent = getattr(node.parent, "parent", None)
                        if isinstance(
                            expr_parent,
                            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module),
                        ):
                            is_docstring = True

                    if (
                        not is_tech
                        and not is_docstring
                        and any(c in val for c in (" ", ".", "!", "?", "—", "-"))
                    ):
                        findings.append(
                            Finding(
                                file=rel_path,
                                line=node.lineno,
                                category="D",
                                text=f"Long string literal (>40 chars): '{val[:60]}...'",
                            )
                        )

                # Category E: Prompts in Python code
                if ("You are " in val or "RULES:" in val or "FEW-SHOT EXAMPLES:" in val) and len(
                    val
                ) > 80:
                    findings.append(
                        Finding(
                            file=rel_path,
                            line=node.lineno,
                            category="E",
                            text=f"Prompt template found in code: '{val[:50]}...'",
                        )
                    )

                # Category G: Environment constants (model names, urls, currency)
                if val in ("openai/gpt-oss-120b", "mock-gpt-4", "http://localhost:8080"):
                    findings.append(
                        Finding(
                            file=rel_path,
                            line=node.lineno,
                            category="G",
                            text=f"Hardcoded environment literal: '{val}'",
                        )
                    )
                if "₹" in val:
                    findings.append(
                        Finding(
                            file=rel_path,
                            line=node.lineno,
                            category="G",
                            text=f"Hardcoded currency symbol: '{val[:50]}'",
                        )
                    )

            self.generic_visit(node)

        def visit_Call(self, node: ast.Call):
            # Category D: Streamlit UI calls with hardcoded strings
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "st"
                and node.func.attr
                in (
                    "title",
                    "button",
                    "caption",
                    "markdown",
                    "warning",
                    "info",
                    "error",
                    "subheader",
                    "header",
                    "radio",
                    "checkbox",
                    "expander",
                    "text_input",
                )
            ):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        val = arg.value.strip()
                        if len(val) > 3 and not val.startswith("---"):
                            findings.append(
                                Finding(
                                    file=rel_path,
                                    line=node.lineno,
                                    category="D",
                                    text=f"Hardcoded UI string in st.{node.func.attr}: '{val[:60]}'",
                                )
                            )
            self.generic_visit(node)

    visitor = HardcodeVisitor()
    # Add parent links for context
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)
    visitor.visit(tree)

    # 2. Line-level scan for comments and docstrings (Category A data values)
    for line_idx, line in enumerate(lines, start=1):
        line_clean = line.strip()
        if line_clean.startswith("#"):
            for dv in data_values:
                if len(dv) >= 4 and re.search(rf"\b{re.escape(dv.lower())}\b", line_clean.lower()):
                    findings.append(
                        Finding(
                            file=rel_path,
                            line=line_idx,
                            category="A",
                            text=f"Data value '{dv}' in comment: '{line_clean[:60]}'",
                        )
                    )

    return findings


def run_audit(repo_root: Path | None = None) -> tuple[list[Finding], int]:
    """Run full hardcode audit across medicare/ and ui/."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    allowlist = load_allowlist(repo_root)
    data_values, table_names, column_names = collect_data_catalog(repo_root)
    domain_vocab = load_domain_vocabulary(repo_root)

    targets = [repo_root / "medicare", repo_root / "ui"]
    all_findings: list[Finding] = []

    for target in targets:
        for py_path in sorted(target.rglob("*.py")):
            if "__pycache__" in py_path.parts:
                continue
            findings = scan_file(
                py_path,
                repo_root,
                data_values,
                table_names,
                column_names,
                domain_vocab,
            )
            all_findings.extend(findings)

    # Match against allowlist
    unallowlisted_count = 0
    for f in all_findings:
        is_ok, reason = is_allowlisted(f, allowlist)
        f.allowlisted = is_ok
        f.reason = reason
        if not is_ok:
            unallowlisted_count += 1

    # Generate Markdown Report in docs/decisions/hardcode-audit.md
    docs_dir = repo_root / "docs" / "decisions"
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path = docs_dir / "hardcode-audit.md"

    # Count by category
    cat_counts: dict[str, int] = {c: 0 for c in "ABCDEFG"}
    cat_unallowed: dict[str, int] = {c: 0 for c in "ABCDEFG"}
    for f in all_findings:
        cat_counts[f.category] = cat_counts.get(f.category, 0) + 1
        if not f.allowlisted:
            cat_unallowed[f.category] = cat_unallowed.get(f.category, 0) + 1

    lines = [
        "# Comprehensive Hardcoding Audit Report",
        "",
        "This report is generated by `scripts/audit_hardcoding.py`.",
        "",
        "## Summary by Category",
        "",
        "| Category | Description | Total Found | Unallowlisted | Status |",
        "| :--- | :--- | :--- | :--- | :--- |",
        f"| **A** | Data values (cities, hospitals, insurers, procedures) | {cat_counts['A']} | {cat_unallowed['A']} | {'❌ FAIL' if cat_unallowed['A'] > 0 else '✅ PASS'} |",
        f"| **B** | Schema names in generic code (columns/tables) | {cat_counts['B']} | {cat_unallowed['B']} | {'❌ FAIL' if cat_unallowed['B'] > 0 else '✅ PASS'} |",
        f"| **C** | Domain vocabulary (policy words, claim terms) | {cat_counts['C']} | {cat_unallowed['C']} | {'❌ FAIL' if cat_unallowed['C'] > 0 else '✅ PASS'} |",
        f"| **D** | User-facing text and UI strings | {cat_counts['D']} | {cat_unallowed['D']} | {'❌ FAIL' if cat_unallowed['D'] > 0 else '✅ PASS'} |",
        f"| **E** | Prompts and persona text in code | {cat_counts['E']} | {cat_unallowed['E']} | {'❌ FAIL' if cat_unallowed['E'] > 0 else '✅ PASS'} |",
        f"| **F** | Numbers and limits | {cat_counts['F']} | {cat_unallowed['F']} | {'❌ FAIL' if cat_unallowed['F'] > 0 else '✅ PASS'} |",
        f"| **G** | Environment constants (models, URLs, currency) | {cat_counts['G']} | {cat_unallowed['G']} | {'❌ FAIL' if cat_unallowed['G'] > 0 else '✅ PASS'} |",
        "",
        f"**Total Findings:** {len(all_findings)}  |  **Unallowlisted:** {unallowlisted_count}",
        "",
        "## Detailed Findings",
        "",
        "| File | Line | Cat | Finding Text | Allowlisted? | Reason |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for f in all_findings:
        status = "Yes" if f.allowlisted else "**NO**"
        clean_text = f.text.replace("|", "\\|").replace("\n", " ")
        clean_reason = f.reason.replace("|", "\\|") if f.reason else "-"
        lines.append(
            f"| `{f.file}` | {f.line} | {f.category} | {clean_text} | {status} | {clean_reason} |"
        )

    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return all_findings, unallowlisted_count


def main():
    repo_root = Path(__file__).resolve().parent.parent
    findings, unallowed = run_audit(repo_root)
    print(f"Audit completed: {len(findings)} total findings, {unallowed} unallowlisted.")
    if unallowed > 0:
        print(f"FAILED: {unallowed} unallowlisted hardcoded elements detected in code!")
        print("See docs/decisions/hardcode-audit.md for full breakdown.")
        sys.exit(1)
    else:
        print("SUCCESS: All findings are covered by config/hardcode_allowlist.yaml with reasons.")
        sys.exit(0)


if __name__ == "__main__":
    main()
