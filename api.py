"""
FastAPI Server Entrypoint for AegisSlick.
Run with:
    python api.py
or:
    uvicorn api:app --reload --port 8000
"""

import uvicorn
from backend.main import app

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
