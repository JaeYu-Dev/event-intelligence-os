"""
Causal Path Engine (Engine 4 — Section 29.4)

Builds structured causal paths from a Root Event through the full economic
transmission chain:
  Root Event → Mechanism/Constraint → Latent Expectation → Entity/Industry
  → Tradable Instrument → Confirmation/Invalidation Event

Each node carries evidence data, probability, supporting sources, and
counterevidence. Each edge explains WHY the connection exists.

The 6-item Mechanism Completeness Checklist is enforced:
  1. Trigger — what fact changed
  2. Constraint — who is affected, why not everyone
  3. Transmission — what economic variable changes (supply/demand/margin/discount/reg)
  4. Exposure — which company/asset is economically exposed
  5. Timing — when will it be reflected/confirmed
  6. Falsifier — what data would break this path
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from api.models import Event, Thesis, ThesisScenario


# ---------------------------------------------------------------------------
# Structured causal path types (matching the spec's 6-layer hierarchy)
# ---------------------------------------------------------------------------

@dataclass
class CausalNode:
    """A single node in the causal path, with evidence and probability."""
    node_id: str
    node_type: str          # "root_event", "mechanism", "latent_factor", "entity", "instrument", "confirmation", "risk"
    label_ko: str           # Korean display name
    label_en: str = ""      # English display name
    description_ko: str = ""  # Longer explanation
    evidence_grade: str = "E0"  # E0-E4
    probability: float = 0.5   # confidence in this node's existence
    evidence_items: list[dict[str, str]] = field(default_factory=list)  # [{type: "article", text: "..."}, ...]
    market_data: list[dict[str, str]] = field(default_factory=list)  # [{symbol: "NVDA", change: "-7.1%"}, ...]
    counterevidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # tickers, sectors, etc.


@dataclass
class CausalEdge:
    """A directed connection between two causal nodes, with explanation."""
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str      # e.g. "CAUSES", "CONSTRAINS", "EXPOSES_TO", "AFFECTS", "CONFIRMS", "INVALIDATES"
    label_ko: str           # Korean explanation of WHY this connection exists
    label_en: str = ""
    evidence_grade: str = "E0"
    strength: float = 1.0    # 1-10
    mechanism_detail: str = ""  # economic reasoning behind this connection
    source_refs: list[str] = field(default_factory=list)


@dataclass
class CausalPath:
    """A complete causal path from root event to instrument + confirmation."""
    path_id: str
    thesis_id: str
    root_event_id: str
    nodes: list[CausalNode] = field(default_factory=list)
    edges: list[CausalEdge] = field(default_factory=list)
    path_score: float = 0.0
    mechanism_summary_ko: str = ""  # natural language summary
    status: str = "research_required"
    expected_lag_hours: dict[str, int] = field(default_factory=lambda: {"low": 24, "high": 120})
    checklist: dict[str, bool] = field(default_factory=lambda: {
        "trigger": False, "constraint": False, "transmission": False,
        "exposure": False, "timing": False, "falsifier": False,
    })
    checklist_notes: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Causal Path Engine
# ---------------------------------------------------------------------------

class CausalPathEngine:
    """
    Builds structured causal paths from thesis core events.

    Follows Engine 4 from the spec exactly:
      - Pipeline schema with 6 layers
      - PathScore formula
      - Mechanism completeness checklist
    """

    # Pre-defined economic mechanism templates per event type
    MECHANISM_TEMPLATES: dict[str, dict[str, str]] = {
        "policy_announcement": {
            "trigger_ko": "정책 발표로 인해 새로운 규제/보조금/의무 조건이 발생했습니다.",
            "constraint_ko": "이 정책의 적용을 받는 기업만 영향권에 들어갑니다. 국내 생산 비율, 인증 보유 여부, 지역 제한 등이 핵심 제약 조건입니다.",
            "transmission_ko": "공급 제약 또는 수요 재분배가 발생합니다. 자격 있는 공급자의 마진이 개선되고, 자격이 없는 경쟁자는 시장에서 배제됩니다.",
            "exposure_ko": "해당 조건을 충족하는 기업의 매출/마진이 직접 영향을 받습니다. 공급망 상위/하위 기업으로 2차 파급됩니다.",
            "timing_ko": "시행일 또는 가이던스 발표 시점에 시장이 재평가합니다. 통상 발표 후 1~4주 내 1차 가격 반영이 일어납니다.",
            "falsifier_ko": "시행 연기, 조건 완화, 예외 조항 추가, 또는 대체 공급 출현 시 이 경로는 무효화됩니다.",
        },
        "filing": {
            "trigger_ko": "공시를 통해 기업의 재무/운영 상태에 대한 새로운 사실이 확인되었습니다.",
            "constraint_ko": "동종 업계 내에서도 기업별 노출도가 다릅니다. 해당 공시의 직접 대상과 간접 영향 기업을 구분해야 합니다.",
            "transmission_ko": "투자/비용 구조 변화가 공급망을 통해 전파됩니다. 장비 발주 감소 → 공급업체 매출 감소 → 2차 협력사 영향.",
            "exposure_ko": "직접 공시 기업과 그 공급망 내 기업들이 경제적 노출을 가집니다. 섹터 ETF도 간접 노출됩니다.",
            "timing_ko": "공시 즉시 1차 반응, 이후 애널리스트 데이/실적발표에서 확인됩니다. 2~3주 내 대부분 가격에 반영됩니다.",
            "falsifier_ko": "후속 공시에서 투자 재개, 수요 회복, 또는 구조적 요인이 아닌 일시적 조정임이 밝혀지면 경로가 약화됩니다.",
        },
        "macro": {
            "trigger_ko": "경제 지표 발표로 거시 환경에 대한 시장의 기대가 업데이트되었습니다.",
            "constraint_ko": "금리·환율·원자재에 민감한 섹터가 먼저 반응합니다. 현금흐름이 안정적인 섹터는 상대적으로 덜 영향받습니다.",
            "transmission_ko": "금리 변화 → 할인율 조정 → 성장주/가치주 리밸런싱. 원자재 가격 → 투입 비용 → 마진 압박 또는 개선.",
            "exposure_ko": "장기채권, 성장주 ETF, 금리 민감 섹터(부동산·유틸리티), 원자재 생산기업이 직접 노출됩니다.",
            "timing_ko": "지표 발표 당일 1차 반응, 이후 파생 지표와 연준 발언으로 확인됩니다. 1~5거래일 내 주요 가격 조정.",
            "falsifier_ko": "다음 달 지표가 반대로 나오거나, 중앙은행이 예상과 다른 스탠스를 취하면 경로가 무효화됩니다.",
        },
        "regulatory": {
            "trigger_ko": "규제 기관의 결정으로 특정 제품/기업의 허가 상태가 변경되었습니다.",
            "constraint_ko": "허가를 받은 기업만 직접 수혜를 봅니다. 경쟁사의 허가 상태, 시장 독점 기간, 적응증 범위가 핵심 변수입니다.",
            "transmission_ko": "규제 승인 → 시장 접근 권한 → 매출 발생 → 기업가치 재평가. 실패 시 파이프라인 가치 소멸.",
            "exposure_ko": "해당 기업 및 동일 적응증/기술 플랫폼을 가진 경쟁사가 노출됩니다. 섹터 ETF도 간접 영향.",
            "timing_ko": "승인 발표 당일 급등, 이후 2~4주에 걸쳐 애널리스트 목표가 조정과 함께 추가 반영.",
            "falsifier_ko": "시판 후 안전성 이슈, 경쟁사 우월한 데이터, 보험 급여 거절 시 경로가 깨집니다.",
        },
        "supply_chain": {
            "trigger_ko": "공급망의 특정 지점에서 생산/물류 차질이 발생했습니다.",
            "constraint_ko": "집중된 공급 지역의 차질이 가장 큰 영향을 줍니다. 대체 공급처가 있는 기업은 상대적으로 보호됩니다.",
            "transmission_ko": "공급 감소 → 현물 가격 상승 → 구매자 비용 증가 → 최종 제품 가격 전가 또는 마진 압박.",
            "exposure_ko": "원자재 생산기업(수혜), 원자재 소비기업(비용 증가), 관련 ETF 및 선물이 노출됩니다.",
            "timing_ko": "차질 발생 즉시 현물 가격 반응, 1~2주 내 선물 곡선 조정, 분기 실적에서 최종 확인.",
            "falsifier_ko": "차질 조기 해소, 대체 공급 확대, 수요 감소로 인한 재고 완충 시 경로가 약화됩니다.",
        },
    }

    DEFAULT_TEMPLATE = {
        "trigger_ko": "새로운 사건이 발생하여 기존 시장 상태가 변경되었습니다.",
        "constraint_ko": "모든 기업이 동일하게 영향받지 않습니다. 특정 조건을 충족하는 기업만이 직접 노출됩니다.",
        "transmission_ko": "경제적 메커니즘을 통해 영향이 전파됩니다.",
        "exposure_ko": "연결된 기업과 자산이 경제적 노출을 가집니다.",
        "timing_ko": "시장은 정보를 점진적으로 반영하며, 주요 확인 시점에서 재평가됩니다.",
        "falsifier_ko": "반대 증거나 조건 변경 시 이 경로는 무효화됩니다.",
    }

    def __init__(self, db: Session):
        self.db = db

    def build_path(self, thesis_id: str) -> dict[str, Any]:
        """
        Build a complete causal path for a thesis.

        Returns structured data with nodes, edges, scores, and narrative.
        """
        thesis = self.db.query(Thesis).filter(Thesis.id == UUID(thesis_id)).first()
        if not thesis:
            return {"error": "Thesis not found"}

        event = self.db.query(Event).filter(Event.id == thesis.core_event_id).first()
        if not event:
            return {"error": "Core event not found"}

        template = self.MECHANISM_TEMPLATES.get(
            event.event_type or "", self.DEFAULT_TEMPLATE
        )

        # ------------------------------------------------------------------
        # Build the 6-layer causal chain
        # ------------------------------------------------------------------
        nodes: list[CausalNode] = []
        edges: list[CausalEdge] = []

        etype = event.event_type or "unknown"
        egrade = event.evidence_grade or "E0"
        tickers = event.related_tickers or []
        sector = event.sector_ko or event.sector or ""
        mechanism = event.mechanism_ko or ""

        evidence_items = self._build_evidence_list(event)
        market_data = self._build_market_data(tickers)

        # Layer 1: Root Event
        n_root = CausalNode(
            node_id=f"{thesis_id}-root",
            node_type="root_event",
            label_ko=event.title_ko or event.title or "",
            description_ko=f"원본 사건. {event.actor_ko or event.actor}이(가) {event.action}.",
            evidence_grade=egrade,
            probability=0.95,
            evidence_items=evidence_items,
            market_data=market_data,
            counterevidence=list(event.counterevidence_ko or []),
            metadata={"event_type": etype, "actor": event.actor or "", "sector": sector},
        )
        nodes.append(n_root)

        # Layer 2: Mechanism / Constraint
        n_mech = CausalNode(
            node_id=f"{thesis_id}-mech",
            node_type="mechanism",
            label_ko="경제적 전파 메커니즘",
            description_ko=template["constraint_ko"],
            evidence_grade=_downgrade_grade(egrade),
            probability=0.80,
            evidence_items=[{
                "type": "mechanism_analysis",
                "text": mechanism,
            }] if mechanism else [],
            metadata={
                "transmission_type": self._classify_transmission(etype, mechanism),
                "constraint_type": "자격 있는 공급자만 수혜",
            },
        )
        nodes.append(n_mech)
        edges.append(CausalEdge(
            edge_id=f"{thesis_id}-e1",
            source_node_id=n_root.node_id,
            target_node_id=n_mech.node_id,
            relation_type="CAUSES",
            label_ko=template["transmission_ko"][:80],
            evidence_grade=_downgrade_grade(egrade),
            strength=7.0,
            mechanism_detail=mechanism[:200] if mechanism else "",
        ))

        # Layer 3: Latent Expectation / Economic Variable
        latent_factor = self._infer_latent_factor(event)
        n_latent = CausalNode(
            node_id=f"{thesis_id}-latent",
            node_type="latent_factor",
            label_ko=latent_factor["ko"],
            description_ko=latent_factor["desc"],
            evidence_grade=_downgrade_grade(egrade, 2),
            probability=0.65,
            metadata={
                "factor_name": latent_factor["en"],
                "related_sensors": latent_factor["sensors"],
            },
        )
        nodes.append(n_latent)
        edges.append(CausalEdge(
            edge_id=f"{thesis_id}-e2",
            source_node_id=n_mech.node_id,
            target_node_id=n_latent.node_id,
            relation_type="AFFECTS",
            label_ko=f"이 메커니즘은 {latent_factor['ko']}에 직접 영향을 줍니다.",
            evidence_grade=_downgrade_grade(egrade, 2),
            strength=6.0,
        ))

        # Layer 4: Entity / Sector
        n_entity = CausalNode(
            node_id=f"{thesis_id}-entity",
            node_type="entity",
            label_ko=sector or "영향받는 산업",
            description_ko=f"{sector} 섹터의 기업들이 이 경제적 변화에 노출됩니다. {', '.join(tickers[:5])} 등이 직접 영향권.",
            evidence_grade=egrade,
            probability=0.70,
            metadata={
                "tickers": tickers[:8],
                "sector": sector,
            },
        )
        nodes.append(n_entity)
        edges.append(CausalEdge(
            edge_id=f"{thesis_id}-e3",
            source_node_id=n_latent.node_id,
            target_node_id=n_entity.node_id,
            relation_type="EXPOSES_TO",
            label_ko=f"{sector} 섹터가 이 잠재 요인의 변화에 경제적으로 노출됩니다.",
            evidence_grade=egrade,
            strength=5.0,
        ))

        # Layer 5: Tradable Instrument
        primary_ticker = tickers[0] if tickers else "N/A"
        n_instrument = CausalNode(
            node_id=f"{thesis_id}-instrument",
            node_type="instrument",
            label_ko=f"거래 대상: {', '.join(tickers[:3])}",
            description_ko=f"{', '.join(tickers[:5])} 등이 이 변화의 직접적 수혜/피해를 봅니다. ETF를 통한 간접 노출도 가능합니다.",
            evidence_grade=egrade,
            probability=0.60,
            market_data=market_data,
            metadata={
                "primary_ticker": primary_ticker,
                "all_tickers": tickers[:8],
            },
        )
        nodes.append(n_instrument)
        edges.append(CausalEdge(
            edge_id=f"{thesis_id}-e4",
            source_node_id=n_entity.node_id,
            target_node_id=n_instrument.node_id,
            relation_type="EXPOSES_TO",
            label_ko=f"{primary_ticker}은(는) 이 섹터 변화에 가장 직접적으로 노출된 거래 가능 자산입니다.",
            evidence_grade=egrade,
            strength=4.0,
        ))

        # Layer 6: Confirmation / Invalidation Events
        next_events = event.next_events_ko or []
        counter_ev = event.counterevidence_ko or []
        confirmation_text = next_events[0] if next_events else "확인 이벤트 대기 중"
        n_confirm = CausalNode(
            node_id=f"{thesis_id}-confirm",
            node_type="confirmation",
            label_ko=f"확인: {confirmation_text}",
            description_ko=f"이 가설이 맞다면 {confirmation_text}에서 확인될 것입니다. 반대로 {'; '.join(counter_ev[:2])}는 이 가설을 무효화할 수 있습니다.",
            evidence_grade="E1",
            probability=0.50,
            evidence_items=[{"type": "calendar", "text": ne} for ne in next_events[:3]],
            counterevidence=list(counter_ev),
        )
        nodes.append(n_confirm)
        edges.append(CausalEdge(
            edge_id=f"{thesis_id}-e5",
            source_node_id=n_instrument.node_id,
            target_node_id=n_confirm.node_id,
            relation_type="CONFIRMS" if next_events else "MONITORS",
            label_ko=f"가격 움직임은 {confirmation_text}에서 확인/반증됩니다.",
            evidence_grade="E1",
            strength=3.0,
        ))

        # ------------------------------------------------------------------
        # Compute PathScore (spec formula)
        # ------------------------------------------------------------------
        grade_rank = {"E4": 1.0, "E3": 0.85, "E2": 0.65, "E1": 0.35, "E0": 0.15}
        e_strength = grade_rank.get(egrade, 0.3)
        m_complete = self._checklist_completeness(event, mechanism, tickers, counter_ev, next_events)
        p_relevance = self._portfolio_relevance(tickers)
        novelty = 1.0 if str(event.id) not in self._thesised_event_ids() else 0.4
        e_impact = self._estimate_impact(event)
        u_reflection = 0.5
        confirmability = 0.7 if next_events else 0.3
        d_observability = 0.6 if tickers else 0.2
        s_risk = max(0.1, 1.0 - e_strength)
        r_penalty = 0.2

        path_score = (
            0.22 * e_strength
            + 0.18 * m_complete
            + 0.15 * p_relevance
            + 0.12 * novelty
            + 0.12 * e_impact
            + 0.10 * u_reflection
            + 0.06 * confirmability
            + 0.05 * d_observability
            - 0.15 * s_risk
            - 0.10 * r_penalty
            - 0.05 * 0.1
        )

        # ------------------------------------------------------------------
        # Build checklist
        # ------------------------------------------------------------------
        checklist = {
            "trigger": True,
            "constraint": True,
            "transmission": bool(mechanism and len(mechanism) > 20),
            "exposure": bool(tickers),
            "timing": bool(next_events),
            "falsifier": bool(counter_ev),
        }
        checklist_notes = {
            "trigger": f"{event.actor_ko or event.actor}이(가) {event.action or '행동'}했습니다.",
            "constraint": f"영향은 {sector} 섹터로 제한됩니다.",
            "transmission": mechanism[:150] if mechanism else "전파 경로 분석 중",
            "exposure": f"{', '.join(tickers[:5])} 등 {len(tickers)}개 종목 노출",
            "timing": confirmation_text,
            "falsifier": counter_ev[0] if counter_ev else "반대 증거 수집 중",
        }

        # ------------------------------------------------------------------
        # Narrative
        # ------------------------------------------------------------------
        narrative_ko = self._build_narrative(event, template, tickers, sector, mechanism, next_events, counter_ev)
        
        # Executive summary (plain language, non-expert friendly)
        executive_summary_ko = self._build_executive_summary(
            event, template, tickers, sector, mechanism, next_events, counter_ev
        )
        
        # Timeline with branching scenarios
        # Scenario distribution from event conditions
        conditions = event.conditions or []
        timeline = self._build_timeline(event, tickers, next_events, conditions)
        bull_p = next((s.get("probability", 0.38) for s in conditions if s.get("name") == "Bull"), 0.38)
        base_p = next((s.get("probability", 0.40) for s in conditions if s.get("name") == "Base"), 0.40)
        bear_p = next((s.get("probability", 0.22) for s in conditions if s.get("name") == "Bear"), 0.22)

        bull_range = next((s.get("price_range", "") for s in conditions if s.get("name") == "Bull"), "")
        bear_range = next((s.get("price_range", "") for s in conditions if s.get("name") == "Bear"), "")

        return {
            "path_id": f"path-{thesis_id}",
            "thesis_id": thesis_id,
            "root_event": {
                "id": str(event.id),
                "title_ko": event.title_ko or event.title or "",
                "event_type": etype,
                "evidence_grade": egrade,
                "urgency": event.urgency or "Medium",
                "sector_ko": sector,
                "mechanism_ko": mechanism,
                "actors_ko": event.actor_ko or event.actor or "",
                "action": event.action or "",
            },
            "nodes": [self._node_to_dict(n) for n in nodes],
            "edges": [self._edge_to_dict(e) for e in edges],
            "path_score": round(path_score, 4),
            "score_breakdown": {
                "evidence_strength": round(e_strength, 4),
                "mechanism_completeness": round(m_complete, 4),
                "portfolio_relevance": round(p_relevance, 4),
                "novelty": round(novelty, 4),
                "expected_impact": round(e_impact, 4),
                "under_reflection_potential": round(u_reflection, 4),
                "confirmability": round(confirmability, 4),
                "data_observability": round(d_observability, 4),
                "speculation_risk": round(s_risk, 4),
                "redundancy_penalty": round(r_penalty, 4),
            },
            "checklist": checklist,
            "checklist_notes": checklist_notes,
            "narrative_ko": narrative_ko,
            "scenario_distribution": {
                "Bull": {"probability": round(bull_p, 3), "price_range": bull_range},
                "Base": {"probability": round(base_p, 3), "price_range": ""},
                "Bear": {"probability": round(bear_p, 3), "price_range": bear_range},
            },
            "expected_lag_hours": {"low": 24, "high": 120},
            "status": thesis.status or "research_required",
            "executive_summary_ko": executive_summary_ko,
            "timeline": timeline,
            "external_scenarios": [],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_evidence_list(self, event: Event) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        if event.source_type:
            items.append({"type": "source", "text": f"출처: {event.source_type} (신뢰도 {event.source_reliability or 0:.0%})"})
        if event.mechanism_ko:
            items.append({"type": "mechanism", "text": event.mechanism_ko[:200]})
        # Add SEC/EDGAR-style reference for filings
        if event.event_type == "filing":
            items.append({"type": "filing", "text": "SEC EDGAR 공시 — 8-K / 10-Q / 10-K 원문 참조"})
        if event.event_type == "policy_announcement":
            items.append({"type": "official", "text": "공식 정부/규제기관 발표 — 원문 참조"})
        return items

    def _build_market_data(self, tickers: list[str]) -> list[dict[str, str]]:
        # In production, fetch from DB. Here use pre-mapped data.
        MOCK_PRICES: dict[str, list[dict[str, str]]] = {
            "NVDA": [{"symbol": "NVDA", "change": "-7.1%", "period": "당일"}, {"symbol": "SOX", "change": "-2.3%", "period": "당일"}],
            "AMD": [{"symbol": "AMD", "change": "-3.2%", "period": "당일"}],
            "TSLA": [{"symbol": "TSLA", "change": "+1.8%", "period": "당일"}],
            "LAC": [{"symbol": "LAC", "change": "+12.3%", "period": "당일"}],
            "XLE": [{"symbol": "XLE", "change": "+3.2%", "period": "당일"}],
            "XBI": [{"symbol": "XBI", "change": "+8.3%", "period": "당일"}],
        }
        result: list[dict[str, str]] = []
        for t in tickers[:5]:
            if t in MOCK_PRICES:
                result.extend(MOCK_PRICES[t])
        return result if result else [{"symbol": "N/A", "change": "데이터 수집 중", "period": "-"}]

    def _infer_latent_factor(self, event: Event) -> dict[str, Any]:
        sector = (event.sector or "").lower()
        etype = event.event_type or ""

        mapping = {
            "semiconductors": {"ko": "AI 투자 기대", "en": "AI Capex Expectation", "desc": "하이퍼스케일러·기업의 AI 인프라 투자 규모에 대한 시장 기대", "sensors": ["NVDA", "SMH", "SOX"]},
            "energy": {"ko": "에너지 공급 타이트니스", "en": "Energy Supply Tightness", "desc": "원유·천연가스의 수급 균형과 지정학적 리스크 프리미엄", "sensors": ["XLE", "USO", "XOM"]},
            "cleantech / battery": {"ko": "배터리 소재 수급", "en": "Battery Material Supply", "desc": "리튬·니켈·코발트 등 배터리 핵심 소재의 수요-공급 균형", "sensors": ["LAC", "ALB", "MP"]},
            "biotech": {"ko": "규제 승인 확률", "en": "Regulatory Approval Probability", "desc": "FDA 등 규제기관의 신약 승인 가능성에 대한 시장 평가", "sensors": ["XBI", "IBB"]},
            "macro / rates": {"ko": "금리 인하 기대", "en": "Rate Cut Expectation", "desc": "연준의 통화정책 전환 시기와 폭에 대한 시장 기대", "sensors": ["TLT", "DXY", "QQQ"]},
            "cybersecurity / cloud": {"ko": "클라우드 보안 수요", "en": "Cloud Security Demand", "desc": "사이버 보안 사고 발생 시 보안 솔루션 수요 변화", "sensors": ["CRWD", "PANW", "FTNT"]},
            "materials": {"ko": "원자재 공급 차질", "en": "Commodity Supply Disruption", "desc": "광산·물류 차질이 원자재 가격에 미치는 영향", "sensors": ["FCX", "SCCO", "COPX"]},
        }

        for key, val in mapping.items():
            if key in sector:
                return val

        return {"ko": "위험 선호도 변화", "en": "Risk Appetite Shift", "desc": "전반적인 시장 위험 선호도의 변화", "sensors": ["SPY", "VIX"]}

    def _classify_transmission(self, etype: str, mechanism: str) -> str:
        keywords = {
            "공급": "supply_constraint",
            "수요": "demand_shift",
            "마진": "margin_impact",
            "금리": "discount_rate",
            "규제": "regulatory_constraint",
            "비용": "cost_structure",
        }
        for kw, label in keywords.items():
            if kw in (mechanism or "") or kw in etype:
                return label
        return "market_sentiment"

    def _checklist_completeness(
        self, event: Event, mechanism: str, tickers: list[str],
        counter_ev: list[str], next_events: list[str],
    ) -> float:
        score = 0
        if event and event.title_ko: score += 1  # trigger
        if mechanism and len(mechanism) > 20: score += 1.5  # constraint + transmission
        if tickers: score += 1  # exposure
        if next_events: score += 0.5  # timing
        if counter_ev: score += 0.5  # falsifier
        return min(1.0, score / 6)

    def _portfolio_relevance(self, tickers: list[str]) -> float:
        positions = self.db.query(api.models.PortfolioPosition).all()
        if not positions:
            return 0.3
        portfolio_tickers = set(p.ticker.upper() for p in positions if p.ticker)
        overlap = set(t.upper() for t in tickers) & portfolio_tickers
        return min(1.0, len(overlap) * 0.25 + 0.3)

    def _thesised_event_ids(self) -> set[str]:
        theses = self.db.query(Thesis).all()
        return {str(t.core_event_id) for t in theses if t.core_event_id}

    def _estimate_impact(self, event: Event) -> float:
        base = 0.5
        if event.urgency == "Critical": base = 0.9
        elif event.urgency == "High": base = 0.7
        high_impact = {"filing", "policy_announcement", "earnings", "regulatory"}
        if event.event_type in high_impact: base *= 1.2
        return min(1.0, base)


    def _build_executive_summary(
        self, event, template, tickers, sector, mechanism, next_events, counter_ev,
    ):
        """Build a plain-language executive summary for non-experts."""
        actor = event.actor_ko or event.actor or "기관"
        action = event.action or "발표"
        grade = event.evidence_grade or "?"
        urgency = event.urgency or "보통"
        conditions = event.conditions or []
        bull_p = next((s.get("probability", 0) for s in conditions if s.get("name") == "Bull"), 0.38)
        bear_p = next((s.get("probability", 0) for s in conditions if s.get("name") == "Bear"), 0.22)
        base_p = max(0.0, 1.0 - bull_p - bear_p)
        direction = "긍정적" if bull_p > bear_p + 0.1 else "부정적" if bear_p > bull_p + 0.1 else "중립적"
        next_check = next_events[0] if next_events else "추후 확인"
        next_checks = ", ".join(next_events[:3]) if next_events else "추후 확인"
        counter = counter_ev[0] if counter_ev else "아직 확인되지 않음"
        counters = "; ".join(counter_ev[:3]) if counter_ev else "아직 수집 중"
        latent = self._infer_latent_factor(event)

        return (
            f"{actor}이(가) {event.title_ko or '새로운 사건'}을(를) {action}하면서, "
            f"{sector or '해당'} 섹터를 중심으로 한 새로운 시장 기대 변화가 나타나고 있습니다. "
            f"이 사건의 핵심 인과 메커니즘은 다음과 같습니다: 먼저 {template['trigger_ko']} "
            f"이어서 {template['constraint_ko']} 이 제약 조건 아래 {template['transmission_ko']} "
            f"결국 {template['exposure_ko']} 따라서 {', '.join(tickers[:3])} 등 "
            f"총 {len(tickers)}개 종목이 직접적으로 영향을 받을 가능성이 높습니다. "
            f"시장이 반영할 잠재 요인은 '{latent['ko']}'이며, "
            f"이 요인은 {', '.join(latent['sensors'][:3])} 등에서 확인할 수 있습니다. "
            f"현재로서는 {direction} 방향의 가격 재평가 가능성이 더 높게 평가되며, "
            f"강세 시나리오 확률은 {(bull_p*100):.0f}%, 기본 시나리오는 {(base_p*100):.0f}%, "
            f"약세 시나리오는 {(bear_p*100):.0f}%입니다. "
            f"이 가설이 맞는지 확인할 다음 이벤트는 {next_checks} 이며, "
            f"반대로 {counters} 같은 신호가 나타나면 가설이 약화되거나 무효화될 수 있습니다. "
            f"현재 증거 등급은 {grade}, 긴급도는 {urgency}입니다. "
            f"실제 포지션을 취하기 전에는 위 확인 이벤트와 반대 증거를 지속적으로 추적하고, "
            f"시장 가격에 이미 어느 정도 반영되었는지도 함께 점검해야 합니다."
        )

    def _build_timeline(self, event, tickers, next_events, conditions):
        """Build a timeline with branching scenarios at key inflection points."""
        timeline = []
        event_type = event.event_type or "event"
        checkpoint_types = {
            "policy_announcement": "정책 발표",
            "regulatory": "규제 결정",
            "filing": "기업 공시",
            "earnings": "실적 발표",
            "macro": "매크로 지표",
            "supply_chain": "공급망 이벤트",
            "prediction_market": "예측시장 시그널",
        }
        timeline.append({
            "time_label": "T0",
            "date": (event.published_at.isoformat() if hasattr(event.published_at, "isoformat") else str(event.published_at)).split("T")[0] if event.published_at else "발표일",
            "checkpoint_type": checkpoint_types.get(event_type, "사건 발생"),
            "title_ko": "사건 발생",
            "description_ko": f"{event.title_ko or event.title}",
            "impact_ko": f"{', '.join(tickers[:3])} 등 관련 종목 즉시 반응",
            "branching": [],
        })
        bull = next((s for s in conditions if s.get("name") == "Bull"), None)
        base = next((s for s in conditions if s.get("name") == "Base"), None)
        bear = next((s for s in conditions if s.get("name") == "Bear"), None)
        for idx, ne in enumerate(next_events[:4]):
            ne_ko = event.next_events_ko[idx] if event.next_events_ko and idx < len(event.next_events_ko) else ne
            branches = []
            if bull:
                branches.append({"name": "Bull", "prob": bull.get("probability", 0.38), "price": bull.get("price_range", ""), "condition": bull.get("conditions", [""])[0] if bull.get("conditions") else "강세 조건 충족"})
            if base:
                branches.append({"name": "Base", "prob": base.get("probability", 0.40), "price": base.get("price_range", ""), "condition": "기본 시나리오 유지"})
            if bear:
                branches.append({"name": "Bear", "prob": bear.get("probability", 0.22), "price": bear.get("price_range", ""), "condition": bear.get("conditions", [""])[0] if bear.get("conditions") else "약세 조건 발생"})
            timeline.append({
                "time_label": f"T+{idx+1}",
                "date": ne[:30],
                "checkpoint_type": "확인 이벤트",
                "title_ko": "확인 이벤트",
                "description_ko": ne_ko,
                "impact_ko": "가격 재평가 및 시나리오 확률 업데이트",
                "branching": branches,
            })
        return timeline

    def _build_narrative(
        self, event: Event, template: dict, tickers: list[str],
        sector: str, mechanism: str, next_events: list[str], counter_ev: list[str],
    ) -> str:
        parts = []
        parts.append(f"## 1. 트리거 (Trigger)\n\n{template['trigger_ko']}\n\n**원본 사건:** {event.title_ko or event.title}\n**행위자:** {event.actor_ko or event.actor}\n**행동:** {event.action or '발표'}\n**증거 등급:** {event.evidence_grade or 'E?'}\n")
        parts.append(f"## 2. 제약 조건 (Constraint)\n\n{template['constraint_ko']}\n\n**영향 섹터:** {sector}\n**핵심 종목:** {', '.join(tickers[:5])}\n")
        parts.append(f"## 3. 전파 경로 (Transmission)\n\n{template['transmission_ko']}\n\n**상세 메커니즘:** {mechanism or '분석 중...'}\n")
        parts.append(f"## 4. 노출 분석 (Exposure)\n\n{template['exposure_ko']}\n\n**직접 노출 종목:** {', '.join(tickers[:5])}\n**2차 노출 가능성:** 공급망 상하위 기업 및 섹터 ETF\n")
        parts.append(f"## 5. 타이밍 (Timing)\n\n{template['timing_ko']}\n\n**다음 확인 이벤트:** {'; '.join(next_events[:3]) if next_events else '확인 이벤트 대기 중'}\n")
        parts.append(f"## 6. 무효화 조건 (Falsifier)\n\n{template['falsifier_ko']}\n\n**반대 증거:** {'; '.join(counter_ev[:3]) if counter_ev else '수집 중'}\n")
        return "\n\n".join(parts)

    def _node_to_dict(self, n: CausalNode) -> dict:
        return {
            "node_id": n.node_id, "node_type": n.node_type,
            "label_ko": n.label_ko, "label_en": n.label_en,
            "description_ko": n.description_ko,
            "evidence_grade": n.evidence_grade, "probability": n.probability,
            "evidence_items": n.evidence_items, "market_data": n.market_data,
            "counterevidence": n.counterevidence, "metadata": n.metadata,
        }

    def _edge_to_dict(self, e: CausalEdge) -> dict:
        return {
            "edge_id": e.edge_id, "source_node_id": e.source_node_id,
            "target_node_id": e.target_node_id, "relation_type": e.relation_type,
            "label_ko": e.label_ko, "label_en": e.label_en,
            "evidence_grade": e.evidence_grade, "strength": e.strength,
            "mechanism_detail": e.mechanism_detail, "source_refs": e.source_refs,
        }


def _downgrade_grade(grade: str, steps: int = 1) -> str:
    order = ["E4", "E3", "E2", "E1", "E0"]
    try:
        idx = order.index(grade)
        return order[min(idx + steps, len(order) - 1)]
    except ValueError:
        return "E1"


# Import needed at module level
import api.models
