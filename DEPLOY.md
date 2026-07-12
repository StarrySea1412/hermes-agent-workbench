# Deploying Hermes Agent Workbench

This repository has two primary services:

- Django backend on port `8000`
- Vite-built frontend served by your chosen static host

## 1. Backend setup

```powershell
cd backend
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py collectstatic --noinput
```

Required environment variables:

- `DB_ENGINE=postgres` for production databases

- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `HERMES_GATEWAY_URL`
- `HERMES_GATEWAY_KEY`

Optional but recommended:

- `DEBUG=false`
- `ALLOWED_HOSTS`
- database connection variables used by your Django settings
- `BRAVE_SEARCH_API_KEY` or `SERPAPI_API_KEY` if you want the `web_search` tool to call a live provider

## 2. Frontend build

```powershell
cd ai-skill-app
npm install
npm run build
```

If the frontend is hosted separately, set:

- `VITE_API_BASE_URL=https://your-backend-host`

## 3. Hermes dependencies

The workbench expects an OpenAI-compatible Hermes Gateway at:

- `HERMES_GATEWAY_URL`

The Settings page and `/api/hermes/monitor` endpoint can verify connectivity.

## 4. Minimum deployment checklist

1. Run Django migrations.
2. Serve `/api/*` from the backend.
3. Serve `ai-skill-app/dist/` from a static host.
4. Mount `media/` if file uploads or exported artifacts should persist.
5. Point the backend at a reachable Hermes Gateway.

## 5. Smoke checks

- `GET /api/health`
- `GET /api/agent-templates`
- `GET /api/tools`
- `GET /api/hermes/monitor`

## 6. Notes

- `web_search` uses Brave Search when `BRAVE_SEARCH_API_KEY` is set, otherwise SerpAPI when `SERPAPI_API_KEY` is set.
- The bid workflow endpoints remain deployable, but the main product surface is the generic agent workbench.
