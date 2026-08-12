"""
Event Progression & Stage Assignment (Spec Section IV & VII)

Detects event progression chains:
  Application Submitted → Application Accepted → Review Started → Approved → Launched
  Rumor → Official Proposal → Board Approval → Regulatory Review → Deal Close

Assigns event_stage based on event_type and current status.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from api.models import Event


# Stage progression chains per event category
STAGE_CHAINS: dict[str, list[str]] = {
    "regulatory": [
        "rumor", "announcement", "application_submitted", "application_accepted",
        "review_started", "deadline_scheduled", "committee_review",
        "approval", "conditional_approval", "rejection", "commercial_launch", "revenue_confirmation",
    ],
    "merger_acquisition": [
        "rumor", "potential_interest", "official_proposal", "board_approval",
        "regulatory_review", "shareholder_vote", "deal_close", "integration",
    ],
    "policy": [
        "policy_comment", "bill_introduced", "committee_approval",
        "floor_vote", "executive_order", "implementation", "corporate_impact",
    ],
    "supply_chain": [
        "contract_announcement", "production_start", "shipment",
        "revenue_recognition", "contract_renewal_or_termination",
    ],
    "litigation": [
        "filing", "court_acceptance", "discovery", "trial",
        "verdict", "appeal", "settlement", "resolution",
    ],
    "earnings": [
        "pre_announcement", "earnings_release", "earnings_call",
        "analyst_revision", "next_quarter_guidance",
    ],
}

# Event stage assignment: keyword → event_stage mapping per category
STAGE_KEYWORDS: dict[str, list[tuple[list[str], str]]] = {
    "regulatory": [
        (["소문", "루머", "rumor", "검토 중"], "rumor"),
        (["신청", "제출", "submitted", "filed application", "BLA", "NDA", "신청서"], "application_submitted"),
        (["접수", "accepted", "수리", "acceptance"], "application_accepted"),
        (["심사", "review", "검토 개시", "review started"], "review_started"),
        (["일정", "schedule", "deadline", "예정", "PDUFA"], "deadline_scheduled"),
        (["위원회", "committee", "adcom", "자문"], "committee_review"),
        (["승인", "approved", "approval", "허가"], "approval"),
        (["조건부", "conditional", "conditional approval"], "conditional_approval"),
        (["거절", "rejected", "denied", "거부", "반려"], "rejection"),
        (["출시", "launch", "commercial", "판매", "상업화"], "commercial_launch"),
        (["매출", "revenue", "실적", "sales", "처방"], "revenue_confirmation"),
    ],
    "merger_acquisition": [
        (["소문", "rumor", "관심", "interest", "검토"], "rumor"),
        (["제안", "proposal", "offer", "제시"], "official_proposal"),
        (["이사회", "board", "승인"], "board_approval"),
        (["규제", "regulatory", "심사", "승인"], "regulatory_review"),
        (["주주", "shareholder", "vote"], "shareholder_vote"),
        (["종결", "close", "완료", "체결", "인수 완료"], "deal_close"),
        (["통합", "integration", "합병"], "integration"),
    ],
    "policy": [
        (["발언", "comment", "언급"], "policy_comment"),
        (["발의", "bill", "introduced"], "bill_introduced"),
        (["위원회", "committee", "통과"], "committee_approval"),
        (["본회의", "floor", "표결"], "floor_vote"),
        (["시행령", "executive", "대통령령"], "executive_order"),
        (["시행", "implementation", "적용", "발효"], "implementation"),
        (["실적", "impact", "영향", "매출"], "corporate_impact"),
    ],
    "supply_chain": [
        (["계약", "contract", "수주", "체결"], "contract_announcement"),
        (["생산", "production", "제조"], "production_start"),
        (["출하", "shipment", "납품", "배송"], "shipment"),
        (["매출", "revenue", "인식"], "revenue_recognition"),
        (["재계약", "renewal", "해지", "termination"], "contract_renewal_or_termination"),
    ],
    "litigation": [
        (["제소", "filing", "소송", "제기"], "filing"),
        (["접수", "accept", "수리"], "court_acceptance"),
        (["증거", "discovery", "개시"], "discovery"),
        (["재판", "trial", "심리"], "trial"),
        (["판결", "verdict", "선고"], "verdict"),
        (["항소", "appeal"], "appeal"),
        (["합의", "settlement", "화해"], "settlement"),
        (["종결", "resolution", "확정"], "resolution"),
    ],
    "earnings": [
        (["예비", "pre-announce", "사전"], "pre_announcement"),
        (["실적", "earnings", "발표", "report"], "earnings_release"),
        (["컨퍼런스콜", "call", "설명회"], "earnings_call"),
        (["수정", "revision", "조정", "상향", "하향"], "analyst_revision"),
        (["가이던스", "guidance", "전망"], "next_quarter_guidance"),
    ],
}


class EventStageService:
    """Assigns event_stage based on event content and type."""

    def __init__(self, db: Session):
        self.db = db

    def assign_stage(self, event: Event) -> str:
        """Auto-assign event_stage based on event_type and text content."""
        category = self._categorize(event)

        # Collect all text for keyword matching
        text_fields = [
            event.title or "", event.title_ko or "",
            event.action or "", event.object or "",
            event.mechanism or "", event.mechanism_ko or "",
        ]
        combined_text = " ".join(text_fields).lower()

        # Check keywords for this category
        if category in STAGE_KEYWORDS:
            for keywords, stage in STAGE_KEYWORDS[category]:
                if any(kw in combined_text for kw in keywords):
                    return stage

        # Fallback: use event_type heuristics
        if event.event_type in ("filing", "regulatory"):
            if "approval" in combined_text or "approved" in combined_text:
                return "approval"
            if "filed" in combined_text or "submitted" in combined_text:
                return "application_submitted"
            if "accepted" in combined_text:
                return "application_accepted"

        if event.event_type in ("policy_announcement", "macro"):
            if "announced" in combined_text or "발표" in combined_text:
                return "implementation" if "시행" in combined_text else "announcement"

        return "detected"  # default

    def _categorize(self, event: Event) -> str:
        """Map event_type to a stage category."""
        etype = (event.event_type or "").lower()

        regulatory_types = {"regulatory", "filing", "biotech", "pharma", "fda"}
        if etype in regulatory_types or any(
            kw in (event.title_ko or "").lower() for kw in ["fda", "승인", "허가", "규제"]
        ):
            return "regulatory"

        if "merger" in etype or "acquisition" in etype:
            return "merger_acquisition"

        policy_types = {"policy_announcement", "policy", "government"}
        if etype in policy_types:
            return "policy"

        supply_types = {"supply_chain", "contract"}
        if etype in supply_types:
            return "supply_chain"

        litigation_types = {"litigation", "lawsuit", "legal"}
        if etype in litigation_types:
            return "litigation"

        if etype in ("earnings", "guidance"):
            return "earnings"

        return "general"

    def find_progression(
        self, event: Event, lookback_days: int = 90
    ) -> list[dict[str, Any]]:
        """
        Find events that precede or follow this event in a progression chain.
        Returns chain of events ordered by stage.
        """
        category = self._categorize(event)
        if category not in STAGE_CHAINS:
            return []

        chain = STAGE_CHAINS[category]
        current_stage = event.event_stage or self.assign_stage(event)
        if current_stage not in chain:
            return []

        current_idx = chain.index(current_stage)

        # Find related events (same actor, similar sector)
        results: list[dict[str, Any]] = []
        all_related = (
            self.db.query(Event)
            .filter(
                Event.id != event.id,
                Event.actor == event.actor,
            )
            .order_by(Event.published_at.asc())
            .all()
        )

        for other in all_related:
            other_stage = other.event_stage or self.assign_stage(other)
            if other_stage in chain:
                other_idx = chain.index(other_stage)
                rel_type = "precedes" if other_idx < current_idx else (
                    "follows" if other_idx > current_idx else "same_stage"
                )
                results.append({
                    "event_id": str(other.id),
                    "title_ko": other.title_ko or other.title or "",
                    "stage": other_stage,
                    "published_at": other.published_at.isoformat() if other.published_at else None,
                    "relationship_type": rel_type,
                })

        return sorted(results, key=lambda x: x["published_at"] or "")
