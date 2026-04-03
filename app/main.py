from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base
from app.routers import auth, connections, queries, results


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Hubble API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(connections.router, prefix="/api/connections", tags=["connections"])
app.include_router(queries.router, prefix="/api/queries", tags=["queries"])
app.include_router(results.router, prefix="/api/results", tags=["results"])


@app.get("/health")
def health():
    return {"status": "ok"}
