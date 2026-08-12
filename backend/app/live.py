"""Fan-out of new readings to connected WebSocket clients.

The MQTT callback runs on paho's network thread, but WebSockets live on the
asyncio event loop. publish_threadsafe() hops from that thread onto the loop,
where each client has its own small queue.
"""

import asyncio


class LiveHub:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._clients: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._clients.discard(queue)

    def publish(self, reading: dict) -> None:
        """Call on the event loop. Slow clients drop messages instead of blocking."""
        for queue in self._clients:
            if queue.full():
                queue.get_nowait()  # drop the oldest
            queue.put_nowait(reading)

    def publish_threadsafe(self, reading: dict) -> None:
        """Call from any thread (e.g. the MQTT callback)."""
        self._loop.call_soon_threadsafe(self.publish, reading)
