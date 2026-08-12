import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import SessionLocal
from api.models import Event, Source, SourceDocument
from api.storage import raw_storage


events_data = [
    {
        "event_type": "policy_announcement",
        "actor": "U.S. Department of Energy",
        "actor_ko": "미국 에너지부",
        "action": "announced",
        "object": "subsidy eligibility conditions",
        "title": "DOE announces expanded EV battery domestic-content subsidy",
        "title_ko": "미 에너지부, 전기차 배터리 국내 생산 보조금 확대 발표",
        "sector": "CleanTech / Battery",
        "sector_ko": "클린테크 / 배터리",
        "evidence_grade": "E4",
        "urgency": "High",
        "status": "Active",
        "related_tickers": ["TSLA", "QS", "LAC", "MP", "ALB"],
        "mechanism": "Domestic-content rules reroute demand toward North American battery-material suppliers, tightening qualified supply.",
        "mechanism_ko": "국내 생산 조건이 북미 배터리 소재 수요를 몰아주면서 '자격 있는 공급'이 줄어듦.",
        "counterevidence": ["ALB already expanded Chile contract", "Tesla vertical integration may absorb margin"],
        "counterevidence_ko": ["ALB가 칠레 계약을 확대한 상태", "테슬라가 수직계열화로 마진을 흡수할 수 있음"],
        "next_events": ["Treasury guidance Jul 10", "ALB Q2 call Jul 17"],
        "next_events_ko": ["재묘부 가이던스 7/10", "ALB 2분기 실적발표 7/17"],
    },
    {
        "event_type": "filing",
        "actor": "TSMC",
        "actor_ko": "TSMC",
        "action": "cut",
        "object": "capex guidance",
        "title": "SEC filing: major semiconductor foundry cuts capex guidance 12%",
        "title_ko": "TSMC, 투자 지침 12% 하향 수정 공시",
        "sector": "Semiconductors",
        "sector_ko": "반도체",
        "evidence_grade": "E4",
        "urgency": "Critical",
        "status": "At Risk",
        "related_tickers": ["NVDA", "AMD", "ASML", "AMAT", "LRCX"],
        "mechanism": "Lower foundry capex directly reduces near-term equipment orders and may signal AI demand deceleration.",
        "mechanism_ko": "파운드리 투자 감소는 단기 장비 주문을 줄이고, AI 수요 둔화 신호로 읽힘.",
        "counterevidence": ["Microsoft reaffirmed datacenter build plans", "HBM supply still sold out"],
        "counterevidence_ko": ["MS, 데이터센터 건설 계획 재확인", "HBM 공급 여전히 매진"],
        "next_events": ["NVDA analyst day Jul 08", "Taiwan export data Jul 12"],
        "next_events_ko": ["엔비디아 애널리스트 데이 7/8", "대만 수출 데이터 7/12"],
    },
    {
        "event_type": "macro",
        "actor": "EIA",
        "actor_ko": "미 EIA",
        "action": "reported",
        "object": "inventory draw",
        "title": "EIA reports surprise crude inventory draw as refining runs pick up",
        "title_ko": "EIA, 정제 가동률 상승에 예상 밖 원유 재고 감소 발표",
        "sector": "Energy",
        "sector_ko": "에너지",
        "evidence_grade": "E3",
        "urgency": "Medium",
        "status": "Watching",
        "related_tickers": ["XLE", "CVX", "XOM", "OXY", "USO"],
        "mechanism": "Inventory draw tightens prompt physical markets and can shift futures curve backwardation.",
        "mechanism_ko": "재고 감소는 현물 시장을 타이트하게 만들고 선물 곡선을 백워데이션으로 전환할 수 있음.",
        "counterevidence": ["Gasoline demand 4-week avg still down YoY", "Strategic reserve release rumor"],
        "counterevidence_ko": ["휘발유 수요 4주 평균 전년 대비 감소", "전략비축유 방출 루머"],
        "next_events": ["OPEC+ JMMC Jul 05", "Cushing storage report Jul 09"],
        "next_events_ko": ["OPEC+ JMMC 7/5", "쿠싱 저장고 보고서 7/9"],
    },
    {
        "event_type": "regulatory",
        "actor": "FDA",
        "actor_ko": "FDA",
        "action": "accepted",
        "object": "accelerated approval filing",
        "title": "FDA accepts Biotech X's accelerated approval filing for oncology asset",
        "title_ko": "FDA, 바이오텍 X 종양 자산 가속 승인 신청 접수",
        "sector": "Biotech",
        "sector_ko": "바이오텍",
        "evidence_grade": "E3",
        "urgency": "High",
        "status": "Strengthening",
        "related_tickers": ["XBI", "IBB", "VRTX", "REGN", "BMY"],
        "mechanism": "Regulatory acceptance starts review clock and often re-rates probability-weighted peak sales.",
        "mechanism_ko": "규제 접수로 심사 시계가 시작되고, 확률 가중 정점 매출이 재평가됨.",
        "counterevidence": ["Competitor readout showed similar PFS but no OS benefit"],
        "counterevidence_ko": ["경쟁사 데이터: PFS 유사 but OS 이점 없음"],
        "next_events": ["Adcom date expected Aug", "Competitor ASCO data Jul 22"],
        "next_events_ko": ["Adcom 일정 8월 예정", "경쟁사 ASCO 데이터 7/22"],
    },
    {
        "event_type": "prediction_market",
        "actor": "Polymarket",
        "actor_ko": "Polymarket",
        "action": "priced",
        "object": "Fed cut probability",
        "title": "Polymarket: Fed cut probability for July jumps to 72% after Powell remarks",
        "title_ko": "Polymarket: 파월 발언 후 7월 금리 인하 확률 72% 급등",
        "sector": "Macro / Rates",
        "sector_ko": "매크로 / 금리",
        "evidence_grade": "E2",
        "urgency": "Medium",
        "status": "Active",
        "related_tickers": ["TLT", "GLD", "DXY", "QQQ", "SIVB"],
        "mechanism": "Rate-cut expectations are a latent factor; Polymarket is one sensor among yields, futures and FX.",
        "mechanism_ko": "금리 인하 기대는 잠재 요인이다. Polymarket은 수익률/선물/FX 중 하나의 센서일 뿐.",
        "counterevidence": ["2Y yield barely moved", "Fed speakers this week hawkish"],
        "counterevidence_ko": ["2년물 수익률 거의 움직임 없음", "이번 주 연준 발언 매파적"],
        "next_events": ["Nonfarm payrolls Jul 03", "CPI Jul 15"],
        "next_events_ko": ["비농업 고용 7/3", "CPI 7/15"],
    },
]


def seed():
    db = SessionLocal()
    try:
        source = db.query(Source).filter(Source.source_name == "manual_seed").first()
        if not source:
            source = Source(source_name="manual_seed", source_tier="B", description="Mock events for UI dev")
            db.add(source)
            db.commit()
            db.refresh(source)

        inserted = 0
        for i, e in enumerate(events_data):
            key = f"seed:{i}"
            if db.query(Event).filter(Event.event_key == key).first():
                continue
            doc = SourceDocument(
                source_id=source.id,
                source_document_id=f"seed:{i}",
                content_hash=f"seedhash{i}",
                raw_payload_ref=raw_storage.put(f"seed content {i}".encode(), key_prefix="seeds"),
                published_at=datetime.utcnow(),
                title=e["title"],
                content_type="text/plain",
                metadata_json={},
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            event = Event(
                event_key=key,
                source_document_ids=[doc.id],
                published_at=datetime.utcnow(),
                first_observed_at=datetime.utcnow(),
                source_type="manual_seed",
                source_reliability=0.85,
                **e,
            )
            db.add(event)
            inserted += 1
        db.commit()
        print(f"Seeded {inserted} events")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
