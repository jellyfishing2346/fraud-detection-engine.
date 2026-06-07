from contextlib import asynccontextmanager

from api.routes.alerts import router as alerts_router
from api.routes.score import router as score_router
from db.models import create_tables
from dotenv import load_dotenv
from fastapi import FastAPI
from ml.predict import load_model

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up fraud detection engine...")
    create_tables()
    load_model()
    print("Ready.")
    yield
    print("Shutting down...")


app = FastAPI(
    title="Fraud Detection Engine",
    description="Real-time transaction fraud scoring API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(score_router, prefix="/v1", tags=["Scoring"])
app.include_router(alerts_router, prefix="/v1", tags=["Alerts"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
