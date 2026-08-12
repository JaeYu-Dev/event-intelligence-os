from typing import Protocol
from datetime import datetime
from pydantic import BaseModel, Field


class RawDocument(BaseModel):
    source_document_id: str
    published_at: datetime | None
    title: str | None
    url: str | None
    content_type: str = "text/html"
    raw_content: bytes
    metadata: dict = Field(default_factory=dict)


class NormalizedDocument(BaseModel):
    source_document_id: str
    published_at: datetime | None
    title: str | None
    url: str | None
    content_type: str
    content_text: str
    metadata: dict = Field(default_factory=dict)


class SourceConnector(Protocol):
    source_name: str
    source_tier: str

    async def fetch_incremental(self, cursor: str | None) -> list[RawDocument]: ...
    async def fetch_by_id(self, source_id: str) -> RawDocument | None: ...
    def normalize(self, raw: RawDocument) -> NormalizedDocument: ...
