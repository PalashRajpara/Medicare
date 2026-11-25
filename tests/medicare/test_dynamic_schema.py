"""Test verifying complete schema agnosticism across the platform.

Demonstrates that the chart builder, SQL executor, tabular formatting, and UI rendering
operate seamlessly on an entirely non-healthcare schema: books(title, author, price, in_stock).
"""

import sqlite3

import pytest

from medicare.domain.models import TableResult
from medicare.medicare.chart import build_chart_spec
from medicare.tools.sql_query import SQLiteQueryTool


@pytest.fixture
def books_db(tmp_path):
    """Fixture creating an arbitrary SQLite database with a books catalog."""
    db_file = str(tmp_path / "books.db")
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE books (
            book_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            price REAL NOT NULL,
            in_stock INTEGER NOT NULL
        );
        """
    )
    books_data = [
        (1, "The Pragmatic Programmer", "David Thomas", 45.0, 1),
        (2, "Clean Code", "Robert C. Martin", 40.0, 1),
        (3, "Design Patterns", "Gang of Four", 55.0, 0),
        (4, "Structure and Interpretation", "Abelson & Sussman", 65.0, 1),
    ]
    cur.executemany("INSERT INTO books VALUES (?, ?, ?, ?, ?)", books_data)
    conn.commit()
    conn.close()
    return db_file


def test_chart_builder_on_arbitrary_schema():
    """Verify build_chart_spec automatically classifies text as label and numeric as measure."""
    table = TableResult(
        columns=["title", "author", "price", "in_stock"],
        rows=[
            ["The Pragmatic Programmer", "David Thomas", 45.0, 1],
            ["Clean Code", "Robert C. Martin", 40.0, 1],
            ["Design Patterns", "Gang of Four", 55.0, 0],
            ["Structure and Interpretation", "Abelson & Sussman", 65.0, 1],
        ],
        row_count=4,
    )

    spec = build_chart_spec(table)
    assert spec is not None
    assert spec.chart_type in ("bar", "grouped_bar")
    # Label column should be chosen from first text column
    assert spec.x_axis in ("title", "author")
    # Y column should be the numeric measure
    assert spec.y_axis in ("price", "in_stock")
    assert len(spec.data) == 4
    for row in spec.data:
        assert spec.x_axis in row
        assert "price" in row


@pytest.mark.asyncio
async def test_sql_query_tool_on_arbitrary_schema(books_db):
    """Verify SQLiteQueryTool executes read-only queries against arbitrary non-healthcare schema."""
    tool = SQLiteQueryTool(db_path=books_db)
    result_str = await tool.execute(
        "SELECT title, author, price FROM books WHERE price > 42 ORDER BY price ASC"
    )

    assert "The Pragmatic Programmer" in result_str
    assert "Structure and Interpretation" in result_str
    assert "Clean Code" not in result_str  # price is 40 <= 42


def test_ui_table_formatter_on_arbitrary_schema():
    """Verify column header humanization handles arbitrary schema columns."""
    from ui.components.results_table import humanize_header

    assert humanize_header("book_id") == "Book Id"
    assert humanize_header("price_usd") == "Price Usd"
    assert humanize_header("in_stock") == "In Stock"
    assert humanize_header("author_full_name") == "Author Full Name"
