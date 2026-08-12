"""FastAPI app: REST endpoints, a live WebSocket, and the MQTT subscriber.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000   (from backend/)
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import db
from .config import Settings
from .live import LiveHub
from .mqtt_worker import MqttWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("backend")


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = db.make_engine(settings.database_url)
        app.state.hub = LiveHub(asyncio.get_running_loop())
        app.state.mqtt = None
        if settings.mqtt_enabled:
            app.state.mqtt = MqttWorker(
                settings.mqtt_host,
                settings.mqtt_port,
                settings.mqtt_topic,
                app.state.engine,
                on_saved=app.state.hub.publish_threadsafe,
            )
            app.state.mqtt.start()
        yield
        if app.state.mqtt is not None:
            app.state.mqtt.stop()
        app.state.engine.dispose()

    app = FastAPI(title="Battery Telemetry API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        try:
            with app.state.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            database_ok = True
        except Exception:
            database_ok = False
        mqtt = app.state.mqtt
        return {
            "status": "ok" if database_ok else "degraded",
            "database": database_ok,
            "mqtt_connected": bool(mqtt and mqtt.connected),
        }

    @app.get("/api/readings/latest")
    def readings_latest():
        reading = db.latest_reading(app.state.engine)
        if reading is None:
            raise HTTPException(status_code=404, detail="no readings yet")
        return reading

    @app.get("/api/readings")
    def readings_list(
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = Query(default=1000, ge=1, le=10_000),
    ):
        """Readings in [start, end] (ISO 8601). Without a window: the newest `limit`."""
        if start and end and start > end:
            raise HTTPException(status_code=400, detail="start must be before end")
        return db.readings_between(app.state.engine, start, end, limit)

    @app.get("/api/stats")
    def stats(start: datetime | None = None, end: datetime | None = None):
        """Min/max/avg voltage and current, and energy (Wh) over a window.

        Defaults to the last hour.
        """
        end = end or datetime.now(timezone.utc)
        start = start or end - timedelta(hours=1)
        if start > end:
            raise HTTPException(status_code=400, detail="start must be before end")
        return db.reading_stats(app.state.engine, start, end)

    @app.get("/api/arbitrage/latest")
    def arbitrage_latest():
        result = db.latest_arbitrage(app.state.engine)
        if result is None:
            raise HTTPException(
                status_code=404, detail="no simulator runs yet; run python -m arbitrage.run"
            )
        return result

    @app.websocket("/ws/live")
    async def live(websocket: WebSocket):
        """Pushes every new reading as JSON as soon as it is stored."""
        await websocket.accept()
        hub: LiveHub = app.state.hub
        queue = hub.subscribe()
        try:
            while True:
                reading = await queue.get()
                await websocket.send_json(reading)
        except WebSocketDisconnect:
            pass
        finally:
            hub.unsubscribe(queue)

    return app


app = create_app(Settings.from_env())
