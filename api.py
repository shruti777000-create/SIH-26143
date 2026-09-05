"""
FastAPI Server Entrypoint for Module 2 Oil Spill Drift Engine.
Run with:
    python api.py
or:
    uvicorn api:app --reload --port 8000
"""

import uvicorn
from module2_drift.api import app

if __name__ == "__main__":
    uvicorn.run("module2_drift.api:app", host="0.0.0.0", port=8000, reload=True)
