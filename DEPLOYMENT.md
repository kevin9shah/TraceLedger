# TraceLedger — Production Deployment Guide

TraceLedger is configured for decoupled cloud deployment:
- **Backend (Python / Flask / Gunicorn)** on **Render** (or Railway / Fly.io)
- **Frontend (Tracing Vellum Parallax Client)** on **Vercel**

---

## 1. Backend Deployment (Render)

### Option A: Blueprints (Automated via `render.yaml`)
1. Push your repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com), click **New +** &rarr; **Blueprint**.
3. Connect your GitHub repository.
4. Render automatically parses `render.yaml` and provisions:
   - **Service Name**: `traceledger-backend`
   - **Runtime**: Python 3.11+
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
   - **Health Check Path**: `/healthz`

### Option B: Manual Web Service
If you prefer setting up manually in Render:
- **Type**: Web Service
- **Root Directory**: `.` (leave blank)
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
- **Environment Variables**:
  | Key | Recommended Value | Notes |
  |---|---|---|
  | `TL_CHAIN_ID` | `137` | Polygon PoS Mainnet |
  | `TL_RPC_URL` | `https://polygon-bor-rpc.publicnode.com` | Public or Alchemy/Infura RPC |
  | `TL_CHAIN_NAME` | `Polygon PoS` | UI display label |
  | `TL_ENABLE_TIGERGRAPH` | `false` | `false` for SQLite graph engine; `true` for TG Savanna |
  | `TL_LLM_PROVIDER` | `stub` | `stub`, `google`, `anthropic`, or `openai` |

Once deployed, copy your Render service URL (e.g., `https://traceledger-backend.onrender.com`).

---

## 2. Frontend Deployment (Vercel)

### Option A: Deploying from Root Repository
1. In the [Vercel Dashboard](https://vercel.com/new), click **Add New Project** and import your GitHub repository.
2. The root `vercel.json` automatically sets:
   - **Output Directory**: `frontend`
   - **Framework Preset**: Other
3. Update the backend proxy URL:
   - In `vercel.json` and `frontend/vercel.json`, replace:
     ```json
     "destination": "https://traceledger-backend.onrender.com/api/:path*"
     ```
     with your actual Render URL from Step 1.
4. Click **Deploy**.

### Option B: Root Directory Set to `frontend`
If you configure **Root Directory** as `frontend` in Vercel project settings:
- Vercel will deploy `frontend/index.html` and `frontend/case.html` with zero build configuration.
- The `frontend/vercel.json` file handles all `/api/*` proxies.

---

## 3. Dynamic API Configuration in Browser

The frontend includes an auto-detection and fallback mechanism:
- By default, all requests route through `/api/*` (proxied by Vercel edge rewrite).
- If testing locally or cross-cloud, click the **API Status Pill** in the top navigation or the **API link** in the footer to enter any custom backend URL (e.g. `http://localhost:5001` or `https://custom-domain.onrender.com/api`).
- The chosen endpoint is persisted in `localStorage`.

---

## 4. Local Full-Stack Verification

To test the decoupled setup locally before deploying:

1. **Start Backend**:
   ```bash
   python wsgi.py
   # Serves on http://127.0.0.1:5001
   ```

2. **Verify Health Endpoint**:
   ```bash
   curl http://127.0.0.1:5001/healthz
   # Response: {"cases": 18, "chain_id": 137, "ok": true}
   ```

3. **Verify API with CORS**:
   ```bash
   curl -I http://127.0.0.1:5001/api/status
   # Confirms Access-Control-Allow-Origin: *
   ```

4. **Serve Frontend**:
   ```bash
   cd frontend
   python -m http.server 3000
   # Open http://localhost:3000 in your browser
   ```

