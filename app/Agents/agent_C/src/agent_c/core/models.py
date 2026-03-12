from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union, Annotated

from pydantic import BaseModel, ConfigDict, Field, conlist


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
    idempotency_key: Optional[str] = Field(default=None, min_length=8)

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


class ACPIntent(ACPBaseEnvelope):
    type: Literal["ACP.Intent"]
    payload: ACPIntentPayload
    idempotency_key: str = Field(..., min_length=8)


class ACPAckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref_event_id: str
    status: Literal["accepted", "rejected", "queued"]
    message: Optional[str] = None


class ACPAck(ACPBaseEnvelope):
    type: Literal["ACP.Ack"]
    payload: ACPAckPayload


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


class ACPStatus(ACPBaseEnvelope):
    type: Literal["ACP.Status"]
    payload: ACPStatusPayload


class ACPResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref_event_id: str
    outcome: Literal["success", "partial", "failure"]
    summary: Optional[str] = None
    artifacts: Optional[Dict[str, Any]] = None


class ACPResult(ACPBaseEnvelope):
    type: Literal["ACP.Result"]
    payload: ACPResultPayload


ACPMessage = Annotated[Union[ACPIntent, ACPAck, ACPStatus, ACPResult], Field(discriminator="type")]


ToolName = Literal["agentb.query", "emit.status", "emit.result"]


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: ToolName
    args: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(..., min_length=6)
    actions: List[ToolCall] = Field(default_factory=list)
    rationale: Optional[str] = None
