"""North Campus Routebook. Run: python app.py, then http://127.0.0.1:8000."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from destinations import DESTINATIONS
from routing import Graph, dijkstra, fare, graph_from_osm, nearest_node

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "osm-cache.json"
BBOX = "28.675,77.193,28.701,77.225"
QUERY = f'[out:json][timeout:35];way["highway"]({BBOX});(._;>;);out body;'
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
LOCK = threading.Lock()
STATE = {"payload": None, "graphs": {}, "fetched_at": None}


def install_osm(payload, fetched_at=None):
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Expected an Overpass JSON object with an elements array.")
    # Validate both profiles before replacing a working cache.
    graphs = {mode: graph_from_osm(payload, mode) for mode in ("walk", "drive")}
    timestamp = fetched_at or datetime.now(timezone.utc).isoformat()
    with LOCK:
        STATE.update(payload=payload, graphs=graphs, fetched_at=timestamp)


def save_cache(payload):
    CACHE.parent.mkdir(exist_ok=True)
    temporary = CACHE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"fetched_at": STATE["fetched_at"], "payload": payload}), encoding="utf-8")
    os.replace(temporary, CACHE)


def load_osm(force=False):
    if STATE["payload"] is not None and not force:
        return
    if CACHE.exists() and not force:
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            install_osm(cached["payload"], cached["fetched_at"])
            return
        except (ValueError, KeyError, TypeError):
            pass
    for endpoint in ENDPOINTS:
        try:
            request = urllib.request.Request(endpoint, data=QUERY.encode(), headers={
                "User-Agent": "NorthCampusRoutebook/1.0 (educational Dijkstra project)",
                "Content-Type": "text/plain; charset=utf-8"})
            with urllib.request.urlopen(request, timeout=42) as response:
                payload = json.load(response)
            install_osm(payload)
            save_cache(payload)
            return
        except (OSError, ValueError, KeyError, TypeError):
            continue
    raise ValueError("Could not download OSM streets. Check your internet connection, import an Overpass JSON file, or select Sample graph to demonstrate Dijkstra offline.")


def sample_graph():
    """Deliberately small teaching graph, NOT a surveyed road network."""
    graph = Graph()
    # Coordinates place the abstract graph around campus for teaching only.
    for i, place in enumerate(DESTINATIONS):
        graph.add_node(chr(65+i), place["lat"], place["lon"])
    # Explicit classroom weights, in metres. They are not real road distances.
    links = [("A","H",450),("A","G",1050),("H","B",400),("H","J",350),
             ("J","I",400),("I","L",700),("I","K",1150),("B","E",180),
             ("E","F",300),("F","G",600),("G","C",420),("C","D",400),
             ("F","K",950),("B","G",650),("L","H",900),("E","J",520)]
    for u, v, weight in links:
        graph.add_edge(u,v,weight,"Sample edge")
        graph.add_edge(v,u,weight,"Sample edge")
    return graph


SAMPLE = sample_graph()


def get_graph(source, mode):
    if source not in {"osm", "sample"}:
        raise ValueError("Select OSM streets or Sample graph.")
    if mode not in {"walk", "erickshaw", "auto"}:
        raise ValueError("Unknown transport mode.")
    if source == "sample":
        return SAMPLE
    if not STATE["graphs"]:
        raise ValueError("Load or import the OSM street network first.")
    return STATE["graphs"]["walk" if mode == "walk" else "drive"]


def graph_summary(graph, source):
    return {"source": source, "vertices": len(graph.nodes), "edges": len(graph.edges),
            "nodes": graph.nodes, "links": graph.edges,
            "fetched_at": STATE["fetched_at"] if source == "osm" else None}


def route(body):
    source, mode = body.get("source", "osm"), body.get("mode", "walk")
    graph = get_graph(source, mode)
    places = {p["id"]: (i, p) for i,p in enumerate(DESTINATIONS)}
    if body.get("start") not in places or body.get("end") not in places:
        raise ValueError("Select a valid start and destination.")
    i, start = places[body["start"]]
    j, end = places[body["end"]]
    if source == "sample":
        u, v, start_gap, end_gap = chr(65+i), chr(65+j), 0, 0
    else:
        u, start_gap = nearest_node(graph, [start["lat"], start["lon"]], outgoing=True)
        v, end_gap = nearest_node(graph, [end["lat"], end["lon"]])
    settings = body.get("fare", {})
    base = float(settings.get("base", 20 if mode == "erickshaw" else 30))
    rate = float(settings.get("per_km", 10 if mode == "erickshaw" else 12))
    included = float(settings.get("included_km", 1))
    if not all(math.isfinite(n) and 0 <= n <= 10000 for n in (base,rate,included)):
        raise ValueError("Fare settings must be finite numbers between 0 and 10000.")
    result = dijkstra(graph, u, v)
    result.update({
        "source": source, "mode": mode, "start": start, "end": end,
        "geometry": [graph.nodes[n] for n in result["path"]],
        "start_snap_m": start_gap, "end_snap_m": end_gap,
        "fare": fare(result["distance_m"], mode, base, rate, included),
        "fare_settings": {"base":base,"per_km":rate,"included_km":included},
        "duration_minutes": result["distance_m"] / ({"walk":4.5,"erickshaw":12,"auto":18}[mode] * 1000 / 60),
        "graph_vertices": len(graph.nodes), "graph_edges": len(graph.edges),
        "fetched_at": STATE["fetched_at"] if source == "osm" else None,
    })
    return result


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        content = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/config":
            return self.respond(200, {"destinations": DESTINATIONS, "osm_ready":bool(STATE["graphs"]),
                                      "query": QUERY, "bbox": BBOX})
        assets = {"/": ("index.html","text/html; charset=utf-8"),
                  "/style.css": ("style.css","text/css; charset=utf-8"),
                  "/app.js": ("app.js","text/javascript; charset=utf-8")}
        if path not in assets:
            return self.respond(404, {"error":"Not found"})
        filename, mime = assets[path]
        content = (ROOT / "static" / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        # This is a local application; refuse cross-origin browser writes.
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return self.respond(403, {"error":"Cross-origin requests are not allowed."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 20_000_000:
                raise ValueError("Request must be between 1 byte and 20 MB.")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object.")
            path = urlsplit(self.path).path
            if path == "/api/load":
                load_osm(bool(body.get("refresh")))
                return self.respond(200, graph_summary(get_graph("osm", body.get("mode","walk")), "osm"))
            if path == "/api/import":
                install_osm(body.get("payload"))
                save_cache(body["payload"])
                return self.respond(200, graph_summary(get_graph("osm", body.get("mode","walk")), "osm"))
            if path == "/api/graph":
                source = body.get("source","osm")
                return self.respond(200, graph_summary(get_graph(source,body.get("mode","walk")), source))
            if path == "/api/route":
                return self.respond(200, route(body))
            self.respond(404, {"error":"Not found"})
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            self.respond(400, {"error": str(error) or "Invalid input."})
        except OSError:
            self.respond(500, {"error":"Could not read or save local data. Check project folder permissions."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if CACHE.exists():
        try:
            load_osm()
        except ValueError:
            pass
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"North Campus Routebook → http://127.0.0.1:{args.port}", flush=True)
    print("Keep this terminal open. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nRoutebook stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
