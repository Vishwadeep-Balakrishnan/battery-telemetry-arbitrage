// Live readings: REST for the initial history, then the WebSocket for new ones.
import { useEffect, useRef, useState } from "react";

import { fetchRecentReadings, liveSocketUrl, Reading } from "./api";

// "live": socket open and readings arriving
// "no-data": socket open, but nothing for a while (telemetry program stopped?)
// "connecting" / "offline": no socket to the backend
export type ConnectionStatus = "connecting" | "live" | "no-data" | "offline";

export interface ChartPoint extends Reading {
  t: number; // timestamp in ms, for the chart's x axis
}

const FLUSH_MS = 500; // redraw charts at most twice a second
const RECONNECT_MS = 2000;
const STALE_MS = 5000; // no reading for this long -> "no-data"

function toPoint(r: Reading): ChartPoint {
  return { ...r, t: Date.parse(r.timestamp) };
}

export function useLiveReadings(windowMinutes: number) {
  const [points, setPoints] = useState<ChartPoint[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const pending = useRef<ChartPoint[]>([]); // received since the last flush
  const lastMessageAt = useRef(0);

  // Initial history for the selected window.
  useEffect(() => {
    let cancelled = false;
    fetchRecentReadings(windowMinutes)
      .then((rows) => {
        if (!cancelled) setPoints(rows.map(toPoint));
      })
      .catch(() => {
        if (!cancelled) setStatus("offline");
      });
    return () => {
      cancelled = true;
    };
  }, [windowMinutes]);

  // WebSocket with automatic reconnect.
  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let stopped = false;

    const connect = () => {
      setStatus("connecting");
      socket = new WebSocket(liveSocketUrl());
      socket.onopen = () => setStatus("no-data");
      socket.onmessage = (event) => {
        pending.current.push(toPoint(JSON.parse(event.data) as Reading));
        lastMessageAt.current = Date.now();
      };
      socket.onclose = () => {
        if (stopped) return;
        setStatus("offline");
        retryTimer = window.setTimeout(connect, RECONNECT_MS);
      };
    };
    connect();

    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  // Periodically move pending readings into state and trim the window.
  useEffect(() => {
    const timer = window.setInterval(() => {
      setStatus((s) => {
        if (s === "offline" || s === "connecting") return s;
        return Date.now() - lastMessageAt.current < STALE_MS ? "live" : "no-data";
      });
      if (pending.current.length === 0) return;
      const fresh = pending.current;
      pending.current = [];
      const cutoff = Date.now() - windowMinutes * 60_000;
      setPoints((old) => [...old, ...fresh].filter((p) => p.t >= cutoff));
    }, FLUSH_MS);
    return () => window.clearInterval(timer);
  }, [windowMinutes]);

  const latest = points.length > 0 ? points[points.length - 1] : null;
  return { points, latest, status };
}
