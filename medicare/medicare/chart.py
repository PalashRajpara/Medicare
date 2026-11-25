"""Chart specification builder for comparative metrics (schema-agnostic)."""

from typing import Any

from medicare.config_loader import get_app_config
from medicare.domain.models import ChartSpec, TableResult


def build_chart_spec(table: TableResult | None) -> ChartSpec | None:
    """Inspect TableResult and construct a JSON-serializable ChartSpec if >= 2 rows.

    Chooses axes purely from the result table itself:
    - x-axis: first text column (entity/label)
    - y-axis: primary numeric measure (preferring avg/total, excluding min/max error bounds)
    - secondary_y-axis: secondary numeric measure
    - color_by: binary 0/1 column or low-cardinality category
    - error_min/max: min/max bound columns

    Returns None if table is None, has fewer than 2 rows, or lacks compatible columns.
    """
    if table is None or table.row_count < 2 or not table.rows:
        return None

    columns = table.columns
    if not columns:
        return None

    # Deduplicate rows while preserving order to prevent duplicate bars/points
    seen_row_tuples: set[tuple[Any, ...]] = set()
    unique_table_rows: list[list[Any]] = []
    for r in table.rows:
        r_tup = tuple(r)
        if r_tup not in seen_row_tuples:
            seen_row_tuples.add(r_tup)
            unique_table_rows.append(r)

    if len(unique_table_rows) < 2:
        return None

    # Classify columns by inspecting data rows
    text_cols: list[str] = []
    numeric_cols: list[str] = []
    binary_cols: list[str] = []

    for idx, col in enumerate(columns):
        col_vals = [r[idx] for r in unique_table_rows if len(r) > idx and r[idx] is not None]
        if not col_vals:
            continue

        # Check binary 0/1 or boolean
        if all(v in (0, 1, True, False, "0", "1") for v in col_vals):
            binary_cols.append(col)
        elif all(isinstance(v, (int, float)) for v in col_vals):
            numeric_cols.append(col)
        elif any(isinstance(v, str) for v in col_vals):
            text_cols.append(col)

    # 1. Determine x-axis (first text column)
    x_axis: str | None = text_cols[0] if text_cols else None
    if not x_axis and columns:
        x_axis = columns[0]

    # 2. Determine error bounds (min/max columns)
    error_min: str | None = None
    error_max: str | None = None
    for col in numeric_cols:
        col_lower = col.lower()
        if "min" in col_lower and not error_min:
            error_min = col
        elif "max" in col_lower and not error_max:
            error_max = col

    # Available measures for y-axis
    available_measures = [c for c in numeric_cols if c not in (error_min, error_max)]
    if not available_measures and numeric_cols:
        available_measures = list(numeric_cols)

    if not available_measures:
        return None

    # 3. Determine y-axis: prefer columns with 'avg' or 'total' or take first available
    y_axis: str | None = None
    for col in available_measures:
        col_lower = col.lower()
        if any(h in col_lower for h in ("avg", "mean", "total", "rate", "cost", "score")):
            y_axis = col
            break
    if not y_axis:
        y_axis = available_measures[0]

    # 4. Determine secondary y-axis
    secondary_y_axis: str | None = None
    for col in available_measures:
        if col != y_axis:
            secondary_y_axis = col
            break

    # 5. Determine color_by: binary flag or secondary low-cardinality column
    color_by: str | None = None
    if binary_cols:
        color_by = binary_cols[0]
    elif len(text_cols) > 1:
        # Check cardinality
        for col in text_cols[1:]:
            c_idx = columns.index(col)
            distinct_vals = {r[c_idx] for r in table.rows if len(r) > c_idx}
            if 1 < len(distinct_vals) <= 4:
                color_by = col
                break

    # Build row dictionaries
    data: list[dict[str, Any]] = []
    for row in unique_table_rows:
        row_dict: dict[str, Any] = {}
        for c_idx, c_name in enumerate(columns):
            row_dict[c_name] = row[c_idx] if c_idx < len(row) else None
        data.append(row_dict)

    app_cfg = get_app_config()
    default_title = app_cfg.get("ui", {}).get("chart_title_default", "Comparative Metrics")
    title = (
        f"{y_axis.replace('_', ' ').title()} by {x_axis.replace('_', ' ').title()}"
        if x_axis and y_axis
        else default_title
    )

    return ChartSpec(
        chart_type="grouped_bar",
        title=title,
        x_axis=x_axis,
        y_axis=y_axis,
        secondary_y_axis=secondary_y_axis,
        color_by=color_by,
        error_min=error_min,
        error_max=error_max,
        data=data,
    )
