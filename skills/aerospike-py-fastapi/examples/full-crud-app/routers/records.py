"""
CRUD, batch, and query endpoints for Aerospike records.

Includes:
- PUT    /records/{pk}        -- Create or update a record
- GET    /records/{pk}        -- Read a record (with optional bin selection)
- DELETE /records/{pk}        -- Delete a record (with optional generation check)
- GET    /records             -- Query with expression filters
- POST   /batch/read          -- Batch read multiple records
- POST   /batch/increment     -- Batch increment a bin on multiple records
- POST   /batch/delete        -- Batch delete multiple records
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

import aerospike_py
from aerospike_py import AsyncClient, exp

from config import settings
from dependencies import get_client
from models import (
    BatchOperateRequest,
    BatchReadRequest,
    BatchRecordResponse,
    MessageResponse,
    RecordCreate,
    RecordResponse,
)

router = APIRouter(tags=["records"])

NS = settings.aerospike_namespace
SET = settings.aerospike_set


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.put("/records/{pk}", response_model=MessageResponse)
async def put_record(
    pk: str,
    body: RecordCreate,
    create_only: bool = False,
    client: AsyncClient = Depends(get_client),
):
    """Create or update a record.

    Set `create_only=true` to error if the record already exists (HTTP 409).
    """
    meta = {"ttl": body.ttl} if body.ttl is not None else None
    policy = None
    if create_only:
        policy = {"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY}

    try:
        await client.put((NS, SET, pk), body.bins, meta=meta, policy=policy)
        return MessageResponse(status="ok", message=f"Record '{pk}' written")
    except aerospike_py.RecordExistsError:
        return JSONResponse(status_code=409, content={"error": "Record already exists"})


@router.get("/records/{pk}", response_model=RecordResponse)
async def get_record(
    pk: str,
    bins: str | None = Query(None, description="Comma-separated bin names to select"),
    client: AsyncClient = Depends(get_client),
):
    """Read a record by primary key.

    Optionally pass `?bins=name,age` to select specific bins.
    """
    try:
        key = (NS, SET, pk)
        if bins:
            bin_list = [b.strip() for b in bins.split(",")]
            record = await client.select(key, bin_list)
        else:
            record = await client.get(key)
        return RecordResponse(
            key=pk,
            bins=record.bins,
            generation=record.meta.gen,
            ttl=record.meta.ttl,
        )
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "Record not found"})


@router.delete("/records/{pk}", response_model=MessageResponse)
async def delete_record(
    pk: str,
    generation: int | None = Query(None, description="Expected generation for optimistic locking"),
    client: AsyncClient = Depends(get_client),
):
    """Delete a record by primary key.

    Pass `?generation=N` to enforce optimistic locking (HTTP 409 on mismatch).
    """
    try:
        meta = None
        policy = None
        if generation is not None:
            meta = {"gen": generation}
            policy = {"gen": aerospike_py.POLICY_GEN_EQ}
        await client.remove((NS, SET, pk), meta=meta, policy=policy)
        return MessageResponse(status="deleted", message=f"Record '{pk}' removed")
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "Record not found"})
    except aerospike_py.RecordGenerationError:
        return JSONResponse(status_code=409, content={"error": "Generation mismatch"})


# ---------------------------------------------------------------------------
# Query with expression filters
# ---------------------------------------------------------------------------


@router.get("/records")
async def query_records(
    min_age: int | None = Query(None, description="Minimum age filter"),
    max_age: int | None = Query(None, description="Maximum age filter"),
    status: str | None = Query(None, description="Status equals filter"),
    limit: int = Query(100, ge=1, le=10000, description="Max records to return"),
    client: AsyncClient = Depends(get_client),
) -> list[dict[str, Any]]:
    """Query records with optional server-side expression filters.

    No secondary index required -- filters are evaluated on the server.
    """
    filters = []
    if min_age is not None:
        filters.append(exp.ge(exp.int_bin("age"), exp.int_val(min_age)))
    if max_age is not None:
        filters.append(exp.le(exp.int_bin("age"), exp.int_val(max_age)))
    if status is not None:
        filters.append(exp.eq(exp.string_bin("status"), exp.string_val(status)))

    query = client.query(NS, SET)
    policy: dict[str, Any] = {"max_records": limit}
    if filters:
        expr = exp.and_(*filters) if len(filters) > 1 else filters[0]
        policy["filter_expression"] = expr

    records = await query.results(policy=policy)
    return [
        {"bins": r.bins, "generation": r.meta.gen, "ttl": r.meta.ttl}
        for r in records
        if r.bins is not None
    ]


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------


@router.post("/batch/read", response_model=list[BatchRecordResponse])
async def batch_read(
    body: BatchReadRequest,
    client: AsyncClient = Depends(get_client),
):
    """Read multiple records in a single network call."""
    keys = [(NS, SET, pk) for pk in body.keys]
    result = await client.batch_read(keys, bins=body.bins)

    records = []
    for i, br in enumerate(result.batch_records):
        if br.result == 0 and br.record is not None:
            _, meta, bins = br.record
            records.append(
                BatchRecordResponse(
                    key=body.keys[i],
                    bins=bins,
                    generation=meta.gen if meta else None,
                    result_code=br.result,
                )
            )
        else:
            records.append(
                BatchRecordResponse(key=body.keys[i], result_code=br.result)
            )
    return records


@router.post("/batch/increment", response_model=MessageResponse)
async def batch_increment(
    body: BatchOperateRequest,
    client: AsyncClient = Depends(get_client),
):
    """Increment a numeric bin on multiple records atomically."""
    keys = [(NS, SET, pk) for pk in body.keys]
    ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": body.bin_name, "val": body.increment}]
    await client.batch_operate(keys, ops)
    return MessageResponse(
        status="ok",
        message=f"Incremented '{body.bin_name}' by {body.increment} on {len(keys)} records",
    )


@router.post("/batch/delete", response_model=MessageResponse)
async def batch_delete(
    keys: list[str],
    client: AsyncClient = Depends(get_client),
):
    """Delete multiple records in a single network call."""
    key_tuples = [(NS, SET, pk) for pk in keys]
    await client.batch_remove(key_tuples)
    return MessageResponse(status="ok", message=f"Deleted {len(keys)} records")
