import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = os.getenv("WINGO_DB_PATH", "/data/wingo.db")
try:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
except Exception:
    DB_PATH = "wingo.db"

app = FastAPI(title="Wingo Pattern API", version="1.0.0",
              description="Manual historical Big/Small analysis. No automatic live Wingo feed or guaranteed predictions.")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.on_event("startup")
def startup():
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT UNIQUE NOT NULL, result TEXT NOT NULL CHECK(result IN ('BIG','SMALL')), created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS predictions (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT NOT NULL, prediction TEXT NOT NULL CHECK(prediction IN ('BIG','SMALL')), actual TEXT, created_at TEXT NOT NULL, settled_at TEXT)")

def side(value: str) -> str:
    value = value.strip().upper()
    value = {"B":"BIG","S":"SMALL"}.get(value, value)
    if value not in ("BIG","SMALL"):
        raise HTTPException(status_code=422, detail="Use BIG or SMALL")
    return value

class ResultIn(BaseModel):
    period: str = Field(..., min_length=1, max_length=100)
    result: str

class BatchIn(BaseModel):
    results: List[ResultIn]

class PredictionIn(BaseModel):
    period: str = Field(..., min_length=1, max_length=100)
    prediction: str

@app.get("/")
def root():
    return {"service":"Wingo Pattern API","status":"running","docs":"/docs","health":"/health",
            "note":"Manual/sample results only; no automatic live Wingo feed."}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/v1/results")
def add_result(item: ResultIn):
    result = side(item.result)
    try:
        with db() as conn:
            conn.execute("INSERT INTO results(period,result,created_at) VALUES(?,?,?)",
                         (item.period, result, datetime.now(timezone.utc).isoformat()))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Period already exists")
    return {"saved":True,"period":item.period,"result":result}

@app.post("/api/v1/results/batch")
def add_batch(payload: BatchIn):
    saved = 0
    with db() as conn:
        for item in payload.results:
            try:
                conn.execute("INSERT INTO results(period,result,created_at) VALUES(?,?,?)",
                             (item.period, side(item.result), datetime.now(timezone.utc).isoformat()))
                saved += 1
            except sqlite3.IntegrityError:
                continue
    return {"saved":saved,"submitted":len(payload.results)}

@app.get("/api/v1/results")
def results(limit: int = 50):
    limit = max(1, min(limit, 500))
    with db() as conn:
        rows = conn.execute("SELECT period,result,created_at FROM results ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    return {"count":len(rows),"results":[dict(r) for r in rows]}

@app.get("/api/v1/analysis")
def analysis(limit: int = 100):
    limit = max(1, min(limit, 500))
    with db() as conn:
        rows = conn.execute("SELECT period,result FROM results ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    vals = [r["result"] for r in reversed(rows)]
    total = len(vals); big = vals.count("BIG"); small = vals.count("SMALL")
    streak_side = vals[-1] if vals else None; streak_len = 0
    for val in reversed(vals):
        if val != streak_side: break
        streak_len += 1
    switches = sum(vals[i] != vals[i-1] for i in range(1,len(vals)))
    return {"sample_size":total,"big_count":big,"small_count":small,
            "big_percent":round(big*100/total,2) if total else None,
            "small_percent":round(small*100/total,2) if total else None,
            "latest_streak":{"side":streak_side,"length":streak_len} if total else None,
            "switches":switches,
            "note":"Historical description only; it cannot reliably predict the next result."}

@app.post("/api/v1/predictions")
def add_prediction(item: PredictionIn):
    with db() as conn:
        cur = conn.execute("INSERT INTO predictions(period,prediction,created_at) VALUES(?,?,?)",
                           (item.period, side(item.prediction), datetime.now(timezone.utc).isoformat()))
    return {"saved":True,"id":cur.lastrowid,"period":item.period,"prediction":side(item.prediction)}

@app.post("/api/v1/predictions/{prediction_id}/settle")
def settle(prediction_id: int, actual: str):
    actual = side(actual)
    with db() as conn:
        cur = conn.execute("UPDATE predictions SET actual=?, settled_at=? WHERE id=? AND actual IS NULL",
                           (actual,datetime.now(timezone.utc).isoformat(),prediction_id))
        if cur.rowcount == 0: raise HTTPException(status_code=404, detail="Prediction not found or already settled")
        row = conn.execute("SELECT prediction,actual FROM predictions WHERE id=?",(prediction_id,)).fetchone()
    return {"settled":True,"correct":row["prediction"] == row["actual"],"actual":row["actual"]}

@app.get("/api/v1/predictions/stats")
def prediction_stats():
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) total, SUM(CASE WHEN actual IS NOT NULL THEN 1 ELSE 0 END) settled, SUM(CASE WHEN actual IS NOT NULL AND prediction=actual THEN 1 ELSE 0 END) correct FROM predictions").fetchone()
    total=row["total"] or 0; settled=row["settled"] or 0; correct=row["correct"] or 0
    return {"total":total,"settled":settled,"correct":correct,
            "accuracy_percent":round(correct*100/settled,2) if settled else None}
