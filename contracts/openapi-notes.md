# OpenAPI Notes

FastAPI exposes the live schema at:

```text
http://127.0.0.1:8090/openapi.json
```

When the backend stabilizes, export this schema into `contracts/openapi.yaml`
and generate frontend DTOs from the contract instead of duplicating TypeScript
interfaces manually.
