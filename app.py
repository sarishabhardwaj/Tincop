"""North Campus Routebook. Run: python app.py, then http://127.0.0.1:8000."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from destinations import DESTINATIONS
from routing import Graph, dijkstra, graph_from_osm, largest_component, nearest_node
from transit import transit_graph, transit_fare, transit_journey
from osm_data import BBOX, QUERY, TRANSIT_QUERY, ENDPOINTS, EXPORT_URL, decode_osm, download_sources, merge_payloads

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "osm-cache.json"
LOCK = threading.Lock()
STATE = {"payload": None, "graphs": {}, "fetched_at": None}


def install_osm(payload, fetched_at=None):
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Expected an Overpass JSON object with an elements array.")
    if payload.get("remark"):
        raise ValueError(f"Overpass returned incomplete data: {payload['remark']}")
    # Transit can be absent in older street-only extracts; walking still works.
    graphs = {"walk": graph_from_osm(payload, "walk")}
    graphs.update({mode: transit_graph(payload, mode) for mode in ("bus", "metro")})
    timestamp = fetched_at or datetime.now(timezone.utc).isoformat()
    with LOCK:
        STATE.update(payload=payload, graphs=graphs, fetched_at=timestamp)


def save_cache(payload):
    CACHE.parent.mkdir(exist_ok=True)
    temporary = CACHE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"fetched_at": STATE["fetched_at"], "payload": payload}), encoding="utf-8")
    os.replace(temporary, CACHE)


def load_osm(force=False, transit=False, cache_only=False):
    if STATE["payload"] is not None and not force and not transit:
        return
    if CACHE.exists() and not force and not transit:
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            install_osm(cached["payload"], cached["fetched_at"])
            return
        except (ValueError, KeyError, TypeError):
            pass
    if cache_only:
        raise ValueError("No saved OSM streets are available yet. Download or import a real OSM extract once, then use Saved roads offline.")
    failures = []
    for provider in download_sources(transit):
        endpoint = provider["url"]
        try:
            request = urllib.request.Request(endpoint, data=provider.get("query", "").encode() if provider.get("query") else None, headers={
                "User-Agent": "NorthCampusRoutebook/1.0 (educational Dijkstra project)",
                "Accept": "application/json", "Content-Type": "text/plain; charset=utf-8"})
            with urllib.request.urlopen(request, timeout=18 if not transit else 30) as response:
                payload = decode_osm(response.read())
            if transit:
                payload = merge_payloads(STATE["payload"], payload)
            install_osm(payload)
            save_cache(payload)
            return
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append(f"{urlsplit(endpoint).hostname}: {error}")
    raise ValueError("Python could not download OSM data. " + " | ".join(failures))


def sample_graph():
    """Deliberately small teaching graph, NOT a surveyed road network."""
    graph = Graph()
    # These are SVG layout units, deliberately NOT landmark coordinates.
    for i, place in enumerate(DESTINATIONS):
        graph.add_node(chr(65+i), 75+(i%4)*170, 75+(i//4)*150)
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


def get_graph(source, mode, allow_empty=False):
    if source not in {"osm", "cached", "sample"}:
        raise ValueError("Select OSM network, Saved roads, or Maths diagram.")
    if mode not in {"walk", "bus", "metro"}:
        raise ValueError("Unknown transport mode.")
    if source == "sample":
        return SAMPLE
    if source == "cached" and not STATE["graphs"]:
        load_osm(cache_only=True)
    if not STATE["graphs"]:
        raise ValueError("Load or import the OSM street network first.")
    graph = STATE["graphs"][mode]
    if not graph.edges and not allow_empty:
        raise ValueError(f"No usable {mode} services with connected stops are present in this extract. Refresh/import transit data or choose Walking. Roads alone cannot establish a {mode} service.")
    return graph


def graph_summary(graph, source):
    return {"source": source, "vertices": len(graph.nodes), "edges": len(graph.edges),
            "nodes": graph.nodes, "links": graph.edges,
            "coordinate_system": "diagram" if source == "sample" else "wgs84",
            "available_modes": [mode for mode,g in STATE["graphs"].items() if g.edges] if source != "sample" else ["walk","bus","metro"],
            "fetched_at": STATE["fetched_at"] if source != "sample" else None}


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
    elif mode == "walk":
        connected = largest_component(graph)
        u, start_gap = nearest_node(graph, [start["lat"], start["lon"]], outgoing=True,allowed=connected)
        v, end_gap = nearest_node(graph, [end["lat"], end["lon"]],allowed=connected)
    settings = body.get("fare", {})
    if not isinstance(settings, dict):
        raise ValueError("Fare options must be an object.")
    if settings.get("bus_type", "ordinary") not in {"ordinary", "ac"}:
        raise ValueError("Choose an ordinary or AC bus ticket.")
    ac = settings.get("bus_type", "ordinary") == "ac"
    if source != 'sample' and mode != 'walk':
        result = transit_journey(STATE['graphs']['walk'],graph,
                                 [start['lat'],start['lon']],[end['lat'],end['lon']],mode)
        start_gap,end_gap=result['start_snap_m'],result['end_snap_m']
    else:
        result = dijkstra(graph, u, v)
    if source != "sample" and any(not edge.get("geometry") or len(edge["geometry"]) < 2 for edge in result["edges"]):
        raise ValueError("A mapped segment is missing its road/track geometry. Reimport the OSM extract; no straight-line substitute will be drawn.")
    # A bus change starts a new ticket. Minimise distance, then estimate the fare.
    legs = []
    for edge in result["edges"]:
        if edge.get('transport',mode) != mode:
            continue
        service = edge.get("service", "Sample service")
        if not legs or legs[-1]["service"] != service:
            legs.append({"service":service,"distance_m":0})
        legs[-1]["distance_m"] += edge.get('distance_m',edge['weight'])
    price = sum(transit_fare(leg["distance_m"],mode,ac) for leg in legs) if mode == "bus" else transit_fare(result.get('ride_distance_m',result['distance_m']),mode)
    geometry = []
    for edge in result["edges"]:
        points = edge.get("geometry", [])
        geometry.extend(points if not geometry else points[1:] if geometry[-1] == points[0] else points)
    if not geometry:
        geometry = [graph.nodes[u]]
    segments = [edge["geometry"] for edge in result["edges"]] if source != "sample" else []
    if source == "sample":
        # Never return a fictional sample path as geographic map geometry.
        geometry, segments = [], []
    result.update({
        "source": source, "mode": mode, "start": start, "end": end,
        "geometry": geometry,
        "segments": segments,
        "coordinate_system": "diagram" if source == "sample" else "wgs84",
        "start_snap_m": start_gap, "end_snap_m": end_gap,
        "fare": price, "fare_settings": {"bus_type":"ac" if ac else "ordinary"}, "legs": legs,
        "duration_minutes": result.get('duration_minutes',result["distance_m"] / (4.5 * 1000 / 60)),
        "graph_vertices": result.get('graph_vertices',len(graph.nodes)),
        "graph_edges": result.get('graph_edges',len(graph.edges)),
        "fetched_at": STATE["fetched_at"] if source != "sample" else None,
    })
    if result.get('route_graph'):
        result['route_graph'].update(source=source,coordinate_system='wgs84',
                                     fetched_at=STATE['fetched_at'],
                                     available_modes=[m for m,g in STATE['graphs'].items() if g.edges])
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
                                      "query": QUERY, "transit_query": TRANSIT_QUERY, "bbox": BBOX,
                                      "endpoints": ENDPOINTS, "sources": download_sources(),
                                      "transit_sources": download_sources(True), "export_url": EXPORT_URL})
        assets = {"/": ("index.html","text/html; charset=utf-8"),
                  "/style.css": ("style.css","text/css; charset=utf-8"),
                  "/app.js": ("app.js","text/javascript; charset=utf-8")}
        if path not in assets:
            return self.respond(404, {"error":"Not found"})
        filename, mime = assets[path]
        content = (ROOT / "static" / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
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
                return self.respond(200, graph_summary(STATE["graphs"].get(body.get("mode"), STATE["graphs"]["walk"]), "osm"))
            if path == "/api/load-transit":
                load_osm(force=True,transit=True)
                return self.respond(200, graph_summary(STATE["graphs"].get(body.get("mode"), STATE["graphs"]["walk"]), "osm"))
            if path == "/api/import":
                payload = decode_osm(body.get("payload", body.get("raw")))
                if body.get("merge"):
                    payload = merge_payloads(STATE["payload"],payload)
                install_osm(payload)
                save_cache(payload)
                return self.respond(200, graph_summary(STATE["graphs"].get(body.get("mode"), STATE["graphs"]["walk"]), "osm"))
            if path == "/api/graph":
                source = body.get("source","osm")
                return self.respond(200, graph_summary(get_graph(source,body.get("mode","walk"),allow_empty=True), source))
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
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as error:
        parser.exit(1, f"Could not start the local server: {error}.\nTry another --port if it is occupied. This app needs permission to open a local socket.\n")
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
