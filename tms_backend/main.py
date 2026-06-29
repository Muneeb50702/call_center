from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import loads, rates, drivers

app = FastAPI(title="TMS Mock Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(loads.router)
app.include_router(rates.router)
app.include_router(drivers.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
