# SLM Deployment Control Panel

A web application to compare container vs VM deployment performance for Small Language Models (SLMs).

## Project Structure

```
├── backend/           # FastAPI backend
│   ├── main.py        # API endpoints
│   ├── requirements.txt
│   └── run.ps1/run.sh # Start scripts
├── frontend/          # React frontend
│   ├── app/           # React components
│   ├── styles/        # CSS styles
│   ├── package.json
│   └── run.ps1/run.sh # Start scripts
└── src/               # Original Figma export (reference)
```

## Prerequisites

- **Python 3.10+** for the backend
- **Node.js 18+** for the frontend
- **Docker** (optional, for container deployment features)

## Quick Start

### 1. Start the Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

The API will be available at `http://localhost:8000`

### 2. Start the Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The frontend will be available at `http://localhost:3000`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/models` | GET | Get available models |
| `/api/technologies` | GET | Get container/VM technologies |
| `/api/status` | GET | Get current deployment status |
| `/api/container/start` | POST | Start container deployment |
| `/api/container/stop` | POST | Stop container deployment |
| `/api/vm/start` | POST | Start VM deployment |
| `/api/vm/stop` | POST | Stop VM deployment |
| `/api/metrics` | GET | Get metrics data |
| `/api/tests` | GET | Get available tests |
| `/api/tests/run` | POST | Run selected tests |
| `/ws/metrics` | WebSocket | Real-time metrics stream |

## Features

- **Deployment Cards**: Start/stop container or VM deployments with different technologies
- **Real-time Metrics**: Live CPU, Memory, and Latency monitoring via WebSocket
- **Metrics Visualization**: Comparative charts using Recharts
- **Test Suite**: Run performance comparison tests
- **Download Data**: Export raw metrics as CSV

## Technologies

### Backend
- FastAPI
- Uvicorn
- WebSocket support
- Docker SDK (optional)

### Frontend
- React 18
- TypeScript
- Vite
- Tailwind CSS
- Radix UI (shadcn/ui components)
- Recharts

## Development

### Backend Development

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development

```bash
cd frontend
npm run dev
```

The frontend dev server proxies `/api` and `/ws` requests to the backend automatically.

## Building for Production

### Frontend

```bash
cd frontend
npm run build
```

Build output will be in `frontend/dist/`.
