"""OTLP/HTTP trace receiver: point an OpenTelemetry exporter at ``<server>/v1/traces``."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
from sqlalchemy.orm import Session

from trace_agent_server.db import get_session
from trace_agent_server.services.otlp import ingest_spans
from trace_agent_server.services.otlp_decode import BodyTooLarge, OtlpDecodeError, decode_traces, decompress

# Not under /api: OTLP exporters append /v1/traces to the endpoint they are given.
router = APIRouter()


@router.post("/v1/traces")
async def receive_traces(request: Request, session: Session = Depends(get_session)) -> Response:
    settings = request.app.state.settings
    if not settings.otlp_enabled:
        raise HTTPException(status_code=404, detail="The OTLP receiver is disabled.")

    limit = settings.otlp_max_body_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail=f"Request body is over {limit} bytes.")

    content_type = request.headers.get("content-type")
    try:
        body = decompress(await request.body(), request.headers.get("content-encoding"), limit)
        spans = decode_traces(body, content_type)
    except BodyTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except OtlpDecodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = ingest_spans(session, spans, capture_full=settings.capture_full_payloads)
    session.commit()

    is_json = (content_type or "").split(";")[0].strip().lower() == "application/json"
    if is_json:
        partial = {"partialSuccess": {"rejectedSpans": result.rejected}} if result.rejected else {}
        return Response(content=json.dumps(partial), media_type="application/json")
    response = ExportTraceServiceResponse()
    if result.rejected:
        response.partial_success.rejected_spans = result.rejected
        response.partial_success.error_message = "Some spans could not be understood."
    return Response(content=response.SerializeToString(), media_type="application/x-protobuf")
