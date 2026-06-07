"""Data Governance — dictionnaire, lineage, PII audit."""

from src.governance.data_dictionary import (
    register_data_dictionary_entry,
    register_lineage,
    get_lineage_for_table,
    get_pii_columns,
    export_table_schema_documentation,
    auto_register_schema,
)

__all__ = [
    "register_data_dictionary_entry",
    "register_lineage",
    "get_lineage_for_table",
    "get_pii_columns",
    "export_table_schema_documentation",
    "auto_register_schema",
]
