# TraceLedger — Render Full-Stack Deployment Guide

TraceLedger can be deployed entirely as a **unified full-stack application on Render**.

Deploying entirely on Render gives you:
- **1 Single Service & 1 URL** for both the frontend UI and backend API.
- **Zero CORS issues or proxy rewrites**: HTML, CSS, assets, and APIs are served from the same origin.
- **Persistent Evidence Engine**: Live Polygon PoS (Chain 137) node calls, SQLite append-only audit trail, and human review actions all run in one unified environment.
- **Full Headless API Access**: External tools can still call `/api/*` anytime.

---

## 1. Quick Deploy on Render (Recommended)

### Option A: 1-Click Blueprint (Automated via `render.yaml`)
1. Push your repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com), click **New +** &rarr; **Blueprint**.
3. Select your GitHub repository.
4. Render will read [`render.yaml`](render.yaml) automatically and configure:
   - **Service Name**: `traceledger`
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
   - **Health Check**: `/healthz`
5. Click **Apply**. Within ~2 minutes, your app is live at `https://traceledger.onrender.com`!

### Option B: Manual Web Service Setup
If creating the service manually:
1. In Render Dashboard, click **New +** &rarr; **Web Service**.
2. Connect your repo and set:
   - **Name**: `traceledger`
   - **Language**: `Python 3`
   - **Region**: `Oregon (US West)` or nearest
   - **Branch**: `main` (or your active branch)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
   - **Health Check Path**: `/healthz`
3. Add the following **Environment Variables**:
   | Key | Value | Purpose |
   |---|---|---|
   | `TL_CHAIN_ID` | `137` | Polygon PoS Mainnet |
   | `TL_RPC_URL` | `https://polygon-bor-rpc.publicnode.com` | Public Bor RPC (or your Alchemy/Infura URL) |
   | `TL_CHAIN_NAME` | `Polygon PoS` | UI display label |
   | `TL_ENABLE_TIGERGRAPH` | `false` | `false` uses local SQLite graph; `true` for TG Savanna |
   | `TL_LLM_PROVIDER` | `stub` | `stub`, `google`, `anthropic`, or `openai` |
4. Click **Create Web Service**.

---

## 2. What Gets Served on Render

Once deployed to Render, your single URL provides everything:
- **`https://<your-app>.onrender.com/`**: The complete Tracing Vellum Parallax landing page, live case intake form with instant USDC/USDT switch, active cases docket, and Act 6 benchmark terminal.
- **`https://<your-app>.onrender.com/case/<case_id>`**: Full evidence graph, discrepancy mapping, and human review form.
- **`https://<your-app>.onrender.com/audit`**: Append-only audit trail.
- **`https://<your-app>.onrender.com/landing`**: Dedicated 3D parallax presentation view.
- **`https://<your-app>.onrender.com/healthz`**: Automated health check endpoint.
- **`https://<your-app>.onrender.com/api/*`**: Headless JSON REST endpoints (`/api/status`, `/api/cases`, `/api/case/new`, etc.).

---

## 3. Local Verification

To run and test the identical setup locally:

```bash
# Start the production WSGI application
python wsgi.py

# Open in browser
http://127.0.0.1:5001/
```
