# API Design

The API namespace is independent:

```text
GET  /health
POST /api/excel/files/check-name
POST /api/excel/files
GET  /api/excel/files
GET  /api/excel/files/{file_id}
GET  /api/excel/files/{file_id}/versions
POST /api/excel/files/{file_id}/versions/{version_id}/activate
GET  /api/excel/versions/{version_id}/sheets
GET  /api/excel/sheets/{sheet_id}/preview
GET  /api/excel/sheets/{sheet_id}/rows/{row_id}
```

Conflict response:

```json
{
  "detail": "file 'workbook.xlsx' already exists",
  "display_name": "workbook.xlsx",
  "file_id": "file_xxx",
  "requires_confirmation": true
}
```

The frontend should upload again with `replace_existing=true` only after explicit
user confirmation.
