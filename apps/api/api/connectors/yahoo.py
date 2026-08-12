from datetime import datetime, timedelta
import yfinance as yf
from api.connectors.base import RawDocument, NormalizedDocument


class YahooPriceConnector:
    source_name = "yahoo_finance"
    source_tier = "B"

    async def fetch_incremental(self, cursor: str | None = None) -> list[RawDocument]:
        # This connector primarily ingests price bars, not documents.
        # Return empty raw docs; ingestion service will call fetch_prices directly.
        return []

    async def fetch_prices(self, symbol: str, period: str = "1mo", interval: str = "1d") -> list[dict]:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        records = []
        for date, row in hist.iterrows():
            records.append({
                "symbol": symbol,
                "timestamp": date.to_pydatetime().replace(tzinfo=None),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        return records

    def normalize(self, raw: RawDocument) -> NormalizedDocument:
        return NormalizedDocument(
            source_document_id=raw.source_document_id,
            published_at=raw.published_at,
            title=raw.title,
            url=raw.url,
            content_type=raw.content_type,
            content_text=raw.raw_content.decode("utf-8", errors="ignore"),
            metadata=raw.metadata,
        )
