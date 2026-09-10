from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import enterprise
from .public_api import router as v1_router

app = FastAPI(
    title="Arbiter Resolution API",
    version="1.0.0-preview",
    description="External resolution infrastructure for governed real-world contracts.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

runtime_config = enterprise.load_runtime_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(runtime_config.cors_origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Arbiter-Key", "X-Arbiter-Tenant", "Idempotency-Key", "X-Request-ID"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or __import__("secrets").token_hex(12)
    response = await call_next(request)
    for key, value in enterprise.security_headers(request_id).items():
        response.headers[key] = value
    return response


@app.get("/health")
def health():
    return {"ok": True, "service": "arbiter-resolution-api", "version": "1.0.0-preview"}


app.include_router(v1_router)
