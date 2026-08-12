import json
import hashlib
from datetime import datetime
from typing import Any
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from api.config import settings
from api.connectors.base import NormalizedDocument


class ScenarioOutput(BaseModel):
    name: str = Field(..., pattern="^(Bull|Base|Bear)$")
    probability: float = Field(..., ge=0, le=1)
    conditions: list[str]
    price_range: str


class EventExtraction(BaseModel):
    event_type: str
    actor: str
    actor_ko: str
    action: str
    object: str
    magnitude_value: float | None
    magnitude_unit: str | None
    effective_date: str | None
    title: str
    title_ko: str
    sector: str
    sector_ko: str
    mechanism: str
    mechanism_ko: str
    related_tickers: list[str]
    scenarios: list[ScenarioOutput]
    counterevidence: list[str]
    counterevidence_ko: list[str]
    next_events: list[str]
    next_events_ko: list[str]
    urgency: str = Field(..., pattern="^(Low|Medium|High|Critical)$")
    evidence_grade: str = Field(..., pattern="^(E0|E1|E2|E3|E4)$")


class EvidenceExtractor:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.model = settings.openai_model

    async def extract(self, doc: NormalizedDocument) -> EventExtraction | None:
        if not self.client:
            return None

        system_prompt = (
            "You are an event extraction engine for an investment intelligence system. "
            "Extract structured facts from the document. Be concise. Output JSON matching the requested schema. "
            "Provide Korean translations for actor, title, sector, mechanism, counterevidence, and next_events. "
            "Do not make price predictions; only extract or infer plausible scenario ranges from the document context. "
            "Evidence grade: E4=official confirmed, E3=official but interpretation, E2=repeated observation, E1=explained mechanism, E0=LLM hypothesis."
        )
        user_prompt = f"Document title: {doc.title or 'N/A'}\nPublished: {doc.published_at}\nSource type: {doc.content_type}\n\nContent:\n{doc.content_text[:8000]}"

        resp = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=EventExtraction,
            temperature=0.2,
        )
        extraction = resp.choices[0].message.parsed
        return extraction


extractor = EvidenceExtractor()
