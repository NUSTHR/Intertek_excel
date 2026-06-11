# Excel Workspace Frontend

Independent Vue/Vite app for Excel asset upload, version inspection, sheet
preview, and row highlighting.

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
