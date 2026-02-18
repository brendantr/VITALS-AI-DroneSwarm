from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Literal, Optional, Union, Annotated

from pydantic import BaseModel, Field, ConfigDict, conlist

# -----------------------------
# ACP v0.2 (v0.2 only)
# -----------------------------

ACPComponent = Literal["AgentA", "AgentB", "AgentC", "AgentD", "GUIAdapter", "MAVLinkRouter"]
ACPTargetComponent = Literal["AgentB", "AgentC", "AgentD", "MAVLinkRouter"]
ACPType = Literal["ACP.Intent", "ACP.Ack", "ACP.Status", "ACP.Result"]


class ACPSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: str = Field(default="VITALS")
    component: ACPComponent
    instance: Optional[str] = None


class ACPTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: ACPTargetComponent
    instance: Optional[str] = None


class ACPBaseEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["acp.v0.2"] = Field(default="acp.v0.2")
    event_id: str = Field(..., min_length=8)
    ts: datetime
    type: ACPType

    corr_id: Optional[str] = None
    span_id: Optional[str] = None

    # v0.2 addition: native idempotency key
    idempotency_key: Optional[str] = Field(
        default=None,
        min_length=8,
        description="Stable key for retry dedupe within a corr_id. Keep stable across retransmits.",
    )

    source: ACPSource
    target: Optional[ACPTarget] = None
    payload: Dict[str, Any]


class IntentKind(str, Enum):
    SearchArea = "SearchArea"
    InvestigatePoint = "InvestigatePoint"
    HoldPosition = "HoldPosition"
    ReturnToHome = "ReturnToHome"


class ACPIntentPayloadConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    avoid_nfz: bool = True
    min_alt_m: Optional[float] = None
    max_alt_m: Optional[float] = None
    time_budget_s: Optional[int] = Field(default=None, ge=0)
    battery_reserve_pct: Optional[int] = Field(default=None, ge=0, le=100)


class ACPIntentAreaPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float
    lon: float


class ACPIntentArea(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sector: Optional[str] = None
    # CHANGE: use constrained list to enforce min length reliably
    polygon_wgs84: Optional[conlist(ACPIntentAreaPoint, min_length=3)] = None


class ACPIntentPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float
    lon: float
    alt_m: Optional[float] = None


class ACPIntentUAVAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uav_id: Optional[str] = None


class ACPIntentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent_kind: IntentKind
    priority: int = Field(default=50, ge=0, le=100)
    constraints: ACPIntentPayloadConstraints = Field(default_factory=ACPIntentPayloadConstraints)
    area: Optional[ACPIntentArea] = None
    point: Optional[ACPIntentPoint] = None
    uav_assignment: Optional[ACPIntentUAVAssignment] = None
    rationale: Optional[str] = None


class ACPAckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref_event_id: str
    status: Literal["accepted", "rejected", "queued"]
    message: Optional[str] = None


class ACPStatusState(str, Enum):
    proposed = "proposed"
    approved = "approved"
    planning = "planning"
    executing = "executing"
    paused = "paused"
    completed = "completed"
    failed = "failed"


class ACPStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref_event_id: str
    state: ACPStatusState
    progress_pct: Optional[int] = Field(default=None, ge=0, le=100)
    detail: Optional[str] = None


class ACPResultArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mission_plan_id: Optional[str] = None
    waypoint_count: Optional[int] = Field(default=None, ge=0)


class ACPResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref_event_id: str
    outcome: Literal["success", "partial", "failure"]
    summary: Optional[str] = None
    artifacts: Optional[ACPResultArtifacts] = None


class ACPIntent(ACPBaseEnvelope):
    type: Literal["ACP.Intent"]
    payload: ACPIntentPayload
    # Require idempotency_key for side-effecting intents
    idempotency_key: str = Field(..., min_length=8)


class ACPAck(ACPBaseEnvelope):
    type: Literal["ACP.Ack"]
    payload: ACPAckPayload


class ACPStatus(ACPBaseEnvelope):
    type: Literal["ACP.Status"]
    payload: ACPStatusPayload


class ACPResult(ACPBaseEnvelope):
    type: Literal["ACP.Result"]
    payload: ACPResultPayload


ACPMessage = Annotated[Union[ACPIntent, ACPAck, ACPStatus, ACPResult], Field(discriminator="type")]

# -----------------------------
# Agent B API v0.1 (Query)
# -----------------------------


class AgentBClientInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: Optional[str] = None
    instance: Optional[str] = None


class AgentBQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema: Literal["agentb.api.v0.1"] = Field(default="agentb.api.v0.1")
    type: Literal["AgentB.QueryRequest"] = Field(default="AgentB.QueryRequest")

    query: str = Field(..., min_length=1)
    n_results: int = Field(default=8, ge=1, le=100)
    k_init: int = Field(default=50, ge=1, le=500)
    rerank: bool = False

    where: Dict[str, Any] = Field(default_factory=dict)
    include_scores: bool = True
    include_metadata: bool = True

    corr_id: Optional[str] = None
    client: Optional[AgentBClientInfo] = None


class AgentBQueryResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rank: int = Field(..., ge=1)
    id: str
    text: str
    metadata: Optional[Dict[str, Any]] = None
    score: Optional[float] = None


class AgentBQueryStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n_results: Optional[int] = None
    k_init: Optional[int] = None
    rerank: Optional[bool] = None
    latency_ms: Optional[float] = None


class AgentBQueryError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Optional[str] = None
    message: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


class AgentBQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema: Literal["agentb.api.v0.1"]
    type: Literal["AgentB.QueryResponse"]

    ok: bool
    query_id: str = Field(..., min_length=8)
    ts: datetime

    corr_id: Optional[str] = None

    results: list[AgentBQueryResultItem] = Field(default_factory=list)
    stats: Optional[AgentBQueryStats] = None
    error: Optional[AgentBQueryError] = None
