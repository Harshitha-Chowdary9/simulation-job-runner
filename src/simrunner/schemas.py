"""Pydantic request/response schemas for the REST API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    params: dict = Field(default_factory=dict)


class StepOut(BaseModel):
    name: str
    status: str
    attempts: int
    output: dict | None
    error: str | None

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: uuid.UUID
    status: str
    params: dict
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobDetail(JobOut):
    steps: list[StepOut]
