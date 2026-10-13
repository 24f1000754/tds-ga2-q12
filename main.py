
import os
import time
import uuid
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Assigned values
RATE_LIMIT = 11
WINDOW_SECONDS = 10

ALLOWED_ORIGINS = [
    "https://app-qsnmp3.example.com",
    "https://exam.sanand.workers.dev",
]

# In-memory rate-limit buckets
buckets = {}
lock = threading.Lock()


@app.middleware("http")
async def request_context_and_rate_limit(request: Request, call_next):
    # Reuse supplied request ID, otherwise generate a UUID
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id

    # Handle OPTIONS without consuming the rate-limit bucket
    if request.method == "OPTIONS":
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    client_id = request.headers.get("x-client-id", "anonymous")
    now = time.monotonic()

    with lock:
        start, count = buckets.get(client_id, (now, 0))

        if now - start >= WINDOW_SECONDS:
            start, count = now, 0

        if count >= RATE_LIMIT:
            retry_after = max(
                1,
                int(WINDOW_SECONDS - (now - start) + 0.999)
            )

            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "request_id": request_id,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-Request-ID": request_id,
                },
            )
            return response

        buckets[client_id] = (start, count + 1)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/ping")
async def ping(request: Request):
    return {
        "email": os.environ.get("STUDENT_EMAIL", ""),
        "request_id": request.state.request_id,
    }


# Keep CORS outside the rate limiter so even 429 responses
# can include the required CORS headers.
app = CORSMiddleware(
    app=app,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Client-ID", "X-Request-ID", "Content-Type"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
