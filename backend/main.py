"""
Rabarba Prompt — FastAPI application entry point.

Run from the backend/ directory:
    uvicorn main:app --reload

The .env file must be in backend/ (same directory as this file).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(
    title="Rabarba Prompt API",
    description="LangGraph-based prompt optimizer for coding agents",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
