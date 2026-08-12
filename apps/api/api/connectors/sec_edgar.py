import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any
import httpx
import feedparser
from api.config import settings
from api.connectors.base import RawDocument, NormalizedDocument, SourceConnector


class SECEdgarConnector:
    source_name = "sec_edgar"
    source_tier = "A"

    def __init__(self):
        self.base_url = "https://www.sec.gov"
        self.headers = {"User-Agent": settings.sec_user_agent}

    async def fetch_incremental(self, cursor: str | None = None) -> list[RawDocument]:
        # EDGAR RSS for recent filings
        rss_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&datea=&dateb=&start=0&count=40&output=atom"
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(rss_url)
            resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        docs: list[RawDocument] = []
        for entry in feed.entries[:20]:
            published = self._parse_date(entry.get("updated") or entry.get("published"))
            link = entry.get("link", "")
            title = entry.get("title", "")
            # Filing detail page HTML
            async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
                detail_resp = await client.get(link)
                detail_resp.raise_for_status()
            docs.append(RawDocument(
                source_document_id=entry.get("id", link),
                published_at=published,
                title=title,
                url=link,
                content_type="text/html",
                raw_content=detail_resp.content,
                metadata={"form_type": "8-K", "company_name": entry.get("author", ""), "entry_link": link},
            ))
            await asyncio.sleep(0.2)  # rate limit
        return docs

    async def fetch_by_id(self, source_id: str) -> RawDocument | None:
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(source_id)
            resp.raise_for_status()
        return RawDocument(
            source_document_id=source_id,
            published_at=datetime.utcnow(),
            url=source_id,
            content_type="text/html",
            raw_content=resp.content,
        )

    def normalize(self, raw: RawDocument) -> NormalizedDocument:
        text = raw.raw_content.decode("utf-8", errors="ignore")
        # Basic HTML stripping
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return NormalizedDocument(
            source_document_id=raw.source_document_id,
            published_at=raw.published_at,
            title=raw.title,
            url=raw.url,
            content_type="text/plain",
            content_text=text[:30000],
            metadata=raw.metadata,
        )

    def _parse_date(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
