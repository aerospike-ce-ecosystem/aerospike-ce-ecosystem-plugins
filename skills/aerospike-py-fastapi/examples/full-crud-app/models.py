"""Pydantic request and response models for the Aerospike FastAPI CRUD app."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RecordCreate(BaseModel):
    """Request body for creating or updating a record."""

    bins: dict[str, Any] = Field(..., examples=[{"name": "Alice", "age": 30}])
    ttl: int | None = Field(None, ge=0, description="TTL in seconds (None = namespace default)")


class BatchReadRequest(BaseModel):
    """Request body for batch read."""

    keys: list[str] = Field(..., examples=[["user-1", "user-2", "user-3"]])
    bins: list[str] | None = Field(None, description="Specific bins to read (None = all)")


class BatchOperateRequest(BaseModel):
    """Request body for batch operate (increment)."""

    keys: list[str] = Field(..., examples=[["user-1", "user-2"]])
    bin_name: str = Field(..., examples=["views"])
    increment: int = Field(1, description="Value to increment by")


class QueryRequest(BaseModel):
    """Request body for query with expression filters."""

    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Filter conditions: {bin_name: value} for equality, {bin_name: [min, max]} for range",
        examples=[{"age": [18, 65], "status": "active"}],
    )
    select_bins: list[str] | None = Field(None, description="Specific bins to return")
    limit: int = Field(100, ge=1, le=10000, description="Maximum records to return")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RecordResponse(BaseModel):
    """Response for a single record."""

    key: str
    bins: dict[str, Any] | None = None
    generation: int
    ttl: int


class BatchRecordResponse(BaseModel):
    """Response for a single record in a batch result."""

    key: str | None = None
    bins: dict[str, Any] | None = None
    generation: int | None = None
    result_code: int = 0


class MessageResponse(BaseModel):
    """Simple status message response."""

    status: str
    message: str | None = None


class ErrorResponse(BaseModel):
    """Error response body."""

    error: str
