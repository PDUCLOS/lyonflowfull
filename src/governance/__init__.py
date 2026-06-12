"""Data Governance — dictionnaire, lineage, PII audit."""

from src.governance.data_dictionary import (
    auto_register_schema,
    export_table_schema_documentation,
    get_lineage_for_table,
    get_pii_columns,
    register_data_dictionary_entry,
    register_lineage,
)

__all__ = [
    "auto_register_schema",
    "export_table_schema_documentation",
    "get_lineage_for_table",
    "get_pii_columns",
    "register_data_dictionary_entry",
    "register_lineage",
]
