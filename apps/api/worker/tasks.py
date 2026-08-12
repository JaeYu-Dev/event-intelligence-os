import asyncio
from worker.main import celery_app
from api.ingest.service import run_connector, ingest_prices


@celery_app.task
def ingest_source(source_name: str) -> dict:
    return asyncio.run(run_connector(source_name))


@celery_app.task
def ingest_price_history(symbol: str, period: str = "1mo", interval: str = "1d") -> dict:
    return asyncio.run(ingest_prices(symbol, period, interval))
