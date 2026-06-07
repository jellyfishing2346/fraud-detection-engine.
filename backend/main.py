import os
import traceback
from contextlib import asynccontextmanager

from api.routes.alerts import router as alerts_router
from api.routes.score import router as score_router
from db.models import create_tables
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from ml.predict import load_model

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up fraud detection engine...")
    create_tables()
    try:
        load_model()
    except Exception as e:
        print(f"Warning: Model not loaded — {e}")
        traceback.print_exc()
    print("Ready.")
    yield
    print("Shutting down...")


app = FastAPI(
    title="Fraud Detection Engine",
    description="Real-time transaction fraud scoring API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(score_router, prefix="/v1", tags=["Scoring"])
app.include_router(alerts_router, prefix="/v1", tags=["Alerts"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.head("/health")
def health_head():
    return {}


@app.get("/dashboard")
def dashboard():
    return FileResponse(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "../frontend/dashboard.html"
        )
    )
