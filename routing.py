"""Weighted directed graphs and Dijkstra, without a routing-library shortcut."""
from dataclasses import dataclass, field
import heapq
import math


def haversine(a, b):
    """Great-circle distance in metres between (latitude, longitude) pairs."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


@dataclass
class Graph:
    nodes: dict = field(default_factory=dict)
    adjacency: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)

    def add_node(self, key, lat, lon):
        self.nodes[str(key)] = [lat, lon]
        self.adjacency.setdefault(str(key), [])

    def add_edge(self, u, v, weight, name="Unnamed way", way_id=None):
        u, v = str(u), str(v)
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("Dijkstra requires finite, non-negative edge weights.")
        edge = {"u": u, "v": v, "weight": weight, "name": name, "way_id": way_id}
        self.adjacency[u].append(edge)
        self.edges.append(edge)


def dijkstra(graph, source, target):
    """Return the shortest path plus an auditable extract-min/relaxation trace.

    An improved vertex is pushed again; stale heap entries are skipped.
    Stop ONLY when the destination is removed from the min-heap and settled.
    """
    if source not in graph.nodes or target not in graph.nodes:
        raise ValueError("Source or destination is not in the graph.")
    distances = {source: 0.0}
    previous, settled, steps = {}, set(), []
    queue = [(0.0, source)]
    while queue:
        distance, u = heapq.heappop(queue)
        if u in settled or distance != distances[u]:
            continue
        settled.add(u)
        step = {"node": u, "distance": distance, "relaxations": []}
        steps.append(step)
        if u == target:
            break
        for edge in graph.adjacency[u]:
            v = edge["v"]
            candidate = distance + edge["weight"]
            if v not in settled and candidate < distances.get(v, math.inf):
                old = distances.get(v)
                distances[v] = candidate
                previous[v] = edge
                heapq.heappush(queue, (candidate, v))
                step["relaxations"].append({"to": v, "old": old, "new": candidate})
    if target not in settled:
        raise ValueError("No connected route was found for this mode. Try another destination or mode.")
    path, path_edges = [target], []
    while path[-1] != source:
        edge = previous[path[-1]]
        path_edges.append(edge)
        path.append(edge["u"])
    return {
        "path": path[::-1], "edges": path_edges[::-1],
        "distance_m": distances[target], "steps": steps,
        "settled_count": len(settled),
        "distances": [{"node": key, "distance": distances.get(key),
                       "settled": key in settled,
                       "previous": previous[key]["u"] if key in previous else None}
                      for key in graph.nodes],
    }


WALKABLE = {"footway", "path", "pedestrian", "steps", "living_street", "residential",
            "service", "unclassified", "tertiary", "secondary", "primary", "track",
            "tertiary_link", "secondary_link", "primary_link", "cycleway"}
DRIVABLE = WALKABLE - {"footway", "path", "pedestrian", "steps", "cycleway", "track"}
DENIED = {"no", "private", "customers", "delivery", "permit", "agricultural", "forestry"}


def permitted(tags, mode):
    highway = tags.get("highway")
    allowed = WALKABLE if mode == "walk" else DRIVABLE
    if highway not in allowed or tags.get("area") == "yes":
        return False
    # Specific access tags override general ones.
    if mode == "walk":
        access = tags.get("foot", tags.get("access", "yes"))
        return access not in DENIED and (highway != "cycleway" or tags.get("foot") in {"yes", "designated", "permissive"})
    access = tags.get("motorcar", tags.get("motor_vehicle", tags.get("vehicle", tags.get("access", "yes"))))
    return access not in DENIED


def graph_from_osm(payload, mode):
    """Every OSM way segment becomes a weighted directed edge.

    Walking ignores vehicle one-way rules; oneway:foot is respected.
    This small educational profile does not implement turn restrictions.
    """
    graph = Graph()
    elements = payload.get("elements", [])
    coords = {str(e["id"]): [e["lat"], e["lon"]] for e in elements if e["type"] == "node"}
    # Exclude explicitly blocked nodes, including barriers with access=no.
    blocked = {str(e["id"]) for e in elements if e["type"] == "node" and
               (e.get("tags", {}).get("foot", e.get("tags", {}).get("access", "yes")) in DENIED
                if mode == "walk" else
                e.get("tags", {}).get("motor_vehicle", e.get("tags", {}).get("vehicle", e.get("tags", {}).get("access", "yes"))) in DENIED)}
    for way in elements:
        tags = way.get("tags", {})
        if way["type"] != "way" or not permitted(tags, mode):
            continue
        direction = tags.get("oneway:foot", "no") if mode == "walk" else tags.get("oneway", "yes" if tags.get("junction") == "roundabout" else "no")
        for u, v in zip(way["nodes"], way["nodes"][1:]):
            u, v = str(u), str(v)
            if u not in coords or v not in coords or u in blocked or v in blocked:
                continue
            for key in (u, v):
                if key not in graph.nodes:
                    graph.add_node(key, *coords[key])
            weight = haversine(coords[u], coords[v])
            name = tags.get("name", tags.get("highway", "Unnamed way").replace("_", " ").title())
            if direction != "-1":
                graph.add_edge(u, v, weight, name, way["id"])
            if direction not in {"yes", "1", "true"}:
                graph.add_edge(v, u, weight, name, way["id"])
    if not graph.edges:
        raise ValueError("The OSM file contains no usable streets for this transport mode.")
    return graph


def nearest_node(graph, coordinate, outgoing=False):
    candidates = (key for key in graph.nodes if not outgoing or graph.adjacency[key])
    try:
        key = min(candidates, key=lambda n: haversine(coordinate, graph.nodes[n]))
    except ValueError:
        raise ValueError("No usable road vertex is available.") from None
    distance = haversine(coordinate, graph.nodes[key])
    if distance > 450:
        raise ValueError("This destination is over 450 m from a usable street. Choose another mode or import a wider OSM extract.")
    return key, distance


def fare(distance_m, mode, base=20, per_km=10, included_km=1):
    if mode == "walk" or distance_m == 0:
        return 0
    values = (base, per_km, included_km, distance_m)
    if not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError("Fare settings must be finite, non-negative numbers.")
    return round(base + max(0, distance_m / 1000 - included_km) * per_km, 2)
