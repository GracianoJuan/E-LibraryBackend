from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from sqlmodel import SQLModel
import os
from dotenv import load_dotenv

from db import engine
from routes import UserRoutes, BookRoutes, HistoryRoutes, RecommendationRoutes
from services.RecService import RecommendationService

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize CBF model
    # Note: Database schema is now managed by Alembic migrations
    # Run "python migration_runner.py upgrade" before starting the app
    try:
        await RecommendationService.initialize_cbf()
    except Exception as e:
        print(f"Warning: Could not initialize CBF model: {e}")
    
    yield


app = FastAPI(lifespan=lifespan)

# Configure CORS - must be first middleware
origins = os.getenv("CLIENT_URL", "http://localhost:3000").split(",")
origins = [origin.strip() for origin in origins]
print(f"CORS Origins: {origins}")  # Debug: print allowed origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_cors_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    allowed_origin = origin if origin in origins else (origins[0] if origins else "*")

    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }

# Global exception handlers to ensure CORS headers are included
@app.middleware("http")
async def error_handler(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        print(f"Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": str(e)},
            headers=get_cors_headers(request),
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=get_cors_headers(request),
    )

# include routers
app.include_router(UserRoutes.router)
app.include_router(BookRoutes.router)
app.include_router(HistoryRoutes.router)
app.include_router(RecommendationRoutes.router)


@app.get("/")
async def root():
    return {"message": "Hello World"}