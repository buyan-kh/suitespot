import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.amenities import router as amenities
from app.images import router as images
from app.images.resize import SIZED_DIR
from app.routers import auth_tokens, cancel, health, logout, register, search

app = FastAPI(title="SuiteSpot API", version="0.1.0")

# Comma-separated. Trailing "/" is stripped because browsers send Origin without one.
CORS_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
# Vercel preview deploys for this project only (team-scoped URLs). Set to "" to disable.
CORS_ORIGIN_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"https://suitespot(-[a-z0-9-]+)?-buyans-projects-56ef48dc\.vercel\.app",
) or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(search.router)
app.include_router(auth_tokens.router)
app.include_router(register.router)
app.include_router(logout.router)
app.include_router(cancel.router)
app.include_router(images.router)
app.include_router(amenities.router)

# Resized hotel photos (1.3.1), built by `python -m app.images` or the seed.
app.mount("/media", StaticFiles(directory=SIZED_DIR, check_dir=False), name="media")
