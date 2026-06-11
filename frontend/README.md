# Excel Workspace Frontend

Independent Vue/Vite app for Excel asset upload, version inspection, sheet
preview, document summaries, session chat, citation navigation, and row
highlighting.

## Current Scope

- Authenticated workspace shell.
- Admin file management and model preference controls.
- Member chat-first workspace with shared file inspection.
- Role-specific default avatars.
- Floating toast notifications for non-blocking file workspace feedback.
- Excel preview, schema inspection, row lookup, and citation click-through.

## Run

Requires Node.js and npm.
 
macOS/Linux:

```bash
cp .env.example .env
npm install
npm run dev
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

Open `http://127.0.0.1:5174`.

Vite proxies `/api` and `/health` to the backend on `127.0.0.1:8090`.
