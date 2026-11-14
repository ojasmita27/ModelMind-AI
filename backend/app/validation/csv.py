"""CSV validation for dataset uploads."""
import csv
import io
from pathlib import Path
from typing import BinaryIO


class CSVValidationError(Exception):
    """Raised when CSV validation fails."""

    def __init__(self, message: str, code: str = "invalid_csv"):
        self.message = message
        self.code = code
        super().__init__(message)


def validate_csv_upload(
    file: BinaryIO,
    filename: str,
    max_size_mb: int,
    allowed_extensions: list[str],
) -> tuple[int, list[str]]:
    """Validate a CSV upload and return row count and column names.

    Raises:
        CSVValidationError: If validation fails.
    """
    # Check file extension
    file_ext = Path(filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise CSVValidationError(
            f"File type '{file_ext}' not allowed. Allowed types: {', '.join(allowed_extensions)}",
            code="invalid_extension",
        )

    # Check file size by reading into memory (for streaming, we'd need to track bytes read)
    file.seek(0, io.SEEK_END)
    file_size_bytes = file.tell()
    file.seek(0)

    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        raise CSVValidationError(
            f"File size ({file_size_bytes / 1024 / 1024:.2f} MB) exceeds maximum allowed size ({max_size_mb} MB).",
            code="file_too_large",
        )

    if file_size_bytes == 0:
        raise CSVValidationError(
            "File is empty.",
            code="empty_file",
        )

    # Parse the COMPLETE file. The upload is already capped at max_size_mb, so
    # reading it into memory is bounded; only the first 8 KB used to be parsed,
    # which produced a truncated row_count and skipped encoding errors later
    # in the file.
    try:
        file.seek(0)
        raw = file.read()

        # Try UTF-8, then UTF-8 with BOM.
        try:
            text_content = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise CSVValidationError(
                    "File encoding is not UTF-8. Please save your file as UTF-8.",
                    code="invalid_encoding",
                )

        text_io = io.StringIO(text_content)

        # Use csv.Sniffer to detect dialect
        sample = text_io.read(1024)
        text_io.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            # Fall back to default
            dialect = csv.excel

        reader = csv.reader(text_io, dialect)

        # Read header
        try:
            header = next(reader)
        except StopIteration:
            raise CSVValidationError(
                "File contains no data.",
                code="no_data",
            )

        if not header or all(col.strip() == "" for col in header):
            raise CSVValidationError(
                "File contains no header row.",
                code="no_header",
            )

        # Check for duplicate columns
        header_lower = [col.strip().lower() for col in header]
        if len(header_lower) != len(set(header_lower)):
            duplicates = [col for col in header_lower if header_lower.count(col) > 1]
            raise CSVValidationError(
                f"Duplicate column names found: {', '.join(set(duplicates))}",
                code="duplicate_columns",
            )

        # Count every data row in the file.
        row_count = 0
        for _ in reader:
            row_count += 1

        if row_count == 0:
            raise CSVValidationError(
                "File contains no data rows.",
                code="no_data_rows",
            )

        # Return row count and column names (stripped)
        columns = [col.strip() for col in header]
        return row_count, columns

    except csv.Error as e:
        raise CSVValidationError(
            f"CSV parsing error: {str(e)}",
            code="csv_parse_error",
        )
