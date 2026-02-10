# -*- coding: utf-8 -*-
"""HTTP API для триггера MR-ревью из GitLab CI."""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from reviewer import run_review

load_dotenv()

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=LOG_LEVEL,
)
log = logging.getLogger("reviewer-api")

REVIEWER_API_TOKEN = os.getenv("REVIEWER_API_TOKEN", "")

app = FastAPI(title="mr-rag-reviewer", version="1.0.0")


class ReviewRequest(BaseModel):
    action: str = Field(default="review_mr")
    project_id: str
    mr_iid: int
    gitlab_url: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/review")
def review(req: ReviewRequest, x_reviewer_token: str | None = Header(default=None)) -> dict:
    if REVIEWER_API_TOKEN and x_reviewer_token != REVIEWER_API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid reviewer token")
    if req.action != "review_mr":
        raise HTTPException(status_code=400, detail="unsupported action")
    try:
        result = run_review(mr_iid=req.mr_iid, project_id=req.project_id, gitlab_url=req.gitlab_url)
        return {"status": "ok", "result": result}
    except Exception as e:
        log.exception("review failed")
        raise HTTPException(status_code=500, detail=str(e))
