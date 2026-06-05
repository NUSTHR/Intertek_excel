# Excel Processing Pipeline

## Upload

1. Receive an Excel workbook.
2. Normalize the display name from the original filename.
3. Check whether another active file uses the same display name.
4. If a match exists and replacement was not confirmed, return `409`.
5. Create a new file when none exists, otherwise create a new version.

## Version Processing

1. Save the original workbook under `storage/files/{file_id}/{version_id}`.
2. Read workbook sheets using the workbook reader adapter.
3. For each sheet:
   - assign `sheet_code`, for example `S001`;
   - export raw CSV;
   - prepend row IDs such as `S001_R25`;
   - write row mappings.
4. Generate profile JSON with sheet names, dimensions, candidate headers, and samples.
5. Mark the version ready and activate it.

## Row Provenance

Row IDs are unique within a sheet. The stable lookup key is:

```text
version_id + sheet_id + row_id
```

The public row ID remains readable:

```text
S001_R25
```

This supports future answer citations and frontend row highlighting.
