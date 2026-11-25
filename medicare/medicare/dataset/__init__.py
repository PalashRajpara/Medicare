"""MediCare Dataset package: schemas, CSV importers, policy indexers, and CLI setup."""

from medicare.medicare.dataset.cli import (
    get_table_counts,
    init_database,
    init_medicare_database,
    main,
)
from medicare.medicare.dataset.csv_import import (
    import_all_csvs,
    import_csv_directory,
    import_csv_to_table,
)
from medicare.medicare.dataset.policy_indexer import (
    chunk_markdown_document,
    chunk_markdown_file,
    index_markdown_policies,
    index_policy_documents,
)
from medicare.medicare.dataset.schema import (
    ALL_DDL_STATEMENTS,
    ALLOWED_COLUMNS,
    ALLOWED_TABLES,
    SCHEMA_DESCRIPTION,
)

__all__ = [
    "ALL_DDL_STATEMENTS",
    "ALLOWED_COLUMNS",
    "ALLOWED_TABLES",
    "SCHEMA_DESCRIPTION",
    "chunk_markdown_document",
    "chunk_markdown_file",
    "get_table_counts",
    "import_all_csvs",
    "import_csv_directory",
    "import_csv_to_table",
    "index_markdown_policies",
    "index_policy_documents",
    "init_database",
    "init_medicare_database",
    "main",
]
