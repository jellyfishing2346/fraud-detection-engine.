import os
import traceback
from contextlib import asynccontextmanager

from api.routes.alerts import router as alerts_router
from api.routes.score import router as score_router
from db.models import create_tables
from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from ml.predict import load_model

load_dotenv()

# Set model paths for backend directory deployment
if not os.getenv("MODEL_PATH"):
    os.environ["MODEL_PATH"] = os.path.join(
        os.path.dirname(__file__), "models/xgb_fraud_v1.joblib"
    )
if not os.getenv("SCALER_MEAN_PATH"):
    os.environ["SCALER_MEAN_PATH"] = os.path.join(
        os.path.dirname(__file__), "models/scaler_mean.npy"
    )
if not os.getenv("SCALER_SCALE_PATH"):
    os.environ["SCALER_SCALE_PATH"] = os.path.join(
        os.path.dirname(__file__), "models/scaler_scale.npy"
    )
if not os.getenv("FEATURES_PATH"):
    os.environ["FEATURES_PATH"] = os.path.join(
        os.path.dirname(__file__), "models/feature_columns.txt"
    )


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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(score_router, prefix="/v1", tags=["Scoring"])
app.include_router(alerts_router, prefix="/v1", tags=["Alerts"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to ensure CORS headers on errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "message": str(exc)},
    )


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
