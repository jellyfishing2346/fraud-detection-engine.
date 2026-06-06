from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load model, connect to Redis
    print("Starting up fraud detection engine...")
    # TODO week 3: load XGBoost model here
    # app.state.model = joblib.load(os.getenv("MODEL_PATH"))
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title="Fraud Detection Engine",
    description="Real-time transaction fraud scoring API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


# TODO week 3: add routers
# from api.routes.score import router as score_router
# from api.routes.alerts import router as alerts_router
# app.include_router(score_router, prefix="/v1")
# app.include_router(alerts_router, prefix="/v1")
