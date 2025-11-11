thonimport json
import logging
import os
from typing import Any, Dict, List

import pandas as pd

class DatasetExporter:
    """
    Export a list of records to different tabular formats.
    Supported formats: json, csv, xlsx, html, xml
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    def _ensure_output_dir(self, output_dir: str) -> str:
        if not os.path.isabs(output_dir):
            output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def _export_json(self, records: List[Dict[str, Any]], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

    def _export_csv(self, records: List[Dict[str, Any]], path: str) -> None:
        df = pd.DataFrame(records)
        df.to_csv(path, index=False)

    def _export_xlsx(self, records: List[Dict[str, Any]], path: str) -> None:
        df = pd.DataFrame(records)
        df.to_excel(path, index=False)

    def _export_html(self, records: List[Dict[str, Any]], path: str) -> None:
        df = pd.DataFrame(records)
        html = df.to_html(index=False, border=0)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    def _export_xml(self, records: List[Dict[str, Any]], path: str) -> None:
        # Simple XML serialization without external dependencies
        def escape(text: str) -> str:
            return (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;")
            )

        lines: List[str] = ['<?xml version="1.0" encoding="UTF-8"?>', "<users>"]
        for record in records:
            lines.append("  <user>")
            for key, value in record.items():
                if value is None:
                    continue
                if isinstance(value, (dict, list)):
                    serialized = escape(json.dumps(value, ensure_ascii=False))
                else:
                    serialized = escape(str(value))
                lines.append(f"    <{key}>{serialized}</{key}>")
            lines.append("  </user>")
        lines.append("</users>")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def export(
        self,
        records: List[Dict[str, Any]],
        fmt: str,
        output_dir: str,
        base_filename: str,
    ) -> str:
        """
        Export records and return the absolute path to the written file.
        """
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise ValueError("records must be a list of dictionaries")

        fmt_normalized = fmt.lower()
        if fmt_normalized not in {"json", "csv", "xlsx", "html", "xml"}:
            raise ValueError(f"Unsupported export format: {fmt}")

        output_dir = self._ensure_output_dir(output_dir)

        extension_map = {
            "json": ".json",
            "csv": ".csv",
            "xlsx": ".xlsx",
            "html": ".html",
            "xml": ".xml",
        }
        extension = extension_map[fmt_normalized]
        path = os.path.join(output_dir, base_filename + extension)

        self.logger.info("Exporting %d records to %s (%s)", len(records), path, fmt_normalized)

        if fmt_normalized == "json":
            self._export_json(records, path)
        elif fmt_normalized == "csv":
            self._export_csv(records, path)
        elif fmt_normalized == "xlsx":
            self._export_xlsx(records, path)
        elif fmt_normalized == "html":
            self._export_html(records, path)
        elif fmt_normalized == "xml":
            self._export_xml(records, path)

        return os.path.abspath(path)