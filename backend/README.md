# Excel Workspace Backend

Independent FastAPI service for Excel asset versioning and row-level
provenance.

## Run

macOS/Linux:

```bash
cp .env.example .env
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

## Quality Checks

macOS/Linux:

```bash
./.venv/bin/python -m ruff check app tests
./.venv/bin/python -m pytest
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m ruff check app tests
.\.venv\Scripts\python -m pytest
```

## Storage

By default runtime files are written under:

```text
excel_workspace/storage/
```

Override with `EXCEL_STORAGE_ROOT` and `EXCEL_DATABASE_PATH`.
