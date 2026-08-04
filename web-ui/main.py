"""웹UI FastAPI 메인 진입점."""
from fastapi import FastAPI

app = FastAPI(title="RCI Web UI")


@app.get("/")
def root():
    return {"status": "ok"}
