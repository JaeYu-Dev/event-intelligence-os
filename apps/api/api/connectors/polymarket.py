import json
from datetime import datetime
import httpx
from api.connectors.base import RawDocument, NormalizedDocument


class PolymarketConnector:
    source_name = "polymarket"
    source_tier = "B"

    def __init__(self):
        self.base_url = "https://gamma-api.polymarket.com"

    async def fetch_incremental(self, cursor: str | None = None) -> list[RawDocument]:
        params = {"active": "true", "closed": "false", "limit": "20", "sort": "volume:desc"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.base_url}/markets", params=params)
            resp.raise_for_status()
        markets = resp.json()
        docs: list[RawDocument] = []
        for market in markets:
            market_id = market.get("slug") or market.get("id")
            title = market.get("question", "")
            docs.append(RawDocument(
                source_document_id=f"polymarket:{market_id}",
                published_at=self._parse_date(market.get("createdAt")),
                title=title,
                url=f"https://polymarket.com/event/{market.get('slug', '')}",
                content_type="application/json",
                raw_content=json.dumps(market, ensure_ascii=False).encode("utf-8"),
                metadata={
                    "market_id": market_id,
                    "volume": market.get("volume"),
                    "liquidity": market.get("liquidity"),
                    "end_date": market.get("endDate"),
                    "resolution_source": market.get("resolutionSource"),
                },
            ))
        return docs

    async def fetch_prices(self, market_id: str, start: datetime, end: datetime) -> list[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/history",
                params={"market": market_id, "start": start.isoformat(), "end": end.isoformat()},
            )
            resp.raise_for_status()
        return resp.json()

    def normalize(self, raw: RawDocument) -> NormalizedDocument:
        try:
            market = json.loads(raw.raw_content.decode("utf-8"))
        except Exception:
            market = {}
        text = f"Polymarket market: {raw.title or ''}. "
        text += f"Question: {market.get('question', '')}. "
        text += f"Description: {market.get('description', '')}. "
        text += f"Resolution source: {market.get('resolutionSource', '')}. "
        text += f"End date: {market.get('endDate', '')}. "
        text += f"Volume: {market.get('volume')}. Liquidity: {market.get('liquidity')}."
        return NormalizedDocument(
            source_document_id=raw.source_document_id,
            published_at=raw.published_at,
            title=raw.title,
            url=raw.url,
            content_type="text/plain",
            content_text=text,
            metadata=raw.metadata,
        )

    def _parse_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
