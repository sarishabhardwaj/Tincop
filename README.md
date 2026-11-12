# Tinkop — North Campus Routebook

A Delhi University North Campus trip planner **and** Python Dijkstra educational lab. Default **Live public OSRM streets** mode fetches walking/driving geometry; select Local OSM graph or Sample graph to run and inspect the repository's original Dijkstra implementation.

## Run

Requires **Python 3.10 or newer**. No pip installation is necessary.

```sh
python app.py
```

Open **http://127.0.0.1:8000** in a browser. On Windows, use `py app.py` if `python` is unavailable. To change the port: `python app.py --port 8080`.

1. Choose a starting point, destination, and walk / auto / metered taxi / metro / bus mode. Default **Live public OSRM streets** gives real walking and driving street geometries without requiring an Overpass download. Metro/bus are explicitly marked unverified with no fare, ETA or invented line.
2. For a local Dijkstra trace, change **Network source** to **Local OSM graph · Dijkstra** (first Overpass request can take up to 90 seconds) or **Sample graph · offline**; use Walk, E-rickshaw (classroom only), or Auto.
3. In the graph lab, use **Next step** or **Play** to watch extract-min and successful edge relaxations. Orange points mark settled vertices. The public OSRM mode does not claim to expose Dijkstra's internal trace.
4. Inspect **Vertices & edges**, filter the adjacency list, or export every edge as CSV. **Save JSON** exports the active result.

The interface uses a large map, cream paper colours, restrained green, and serif headings. It works on desktop and mobile. Python performs all route calculations; JavaScript only manages the map and interface.

## Public trip estimates and limitations

- **Foot route:** `routing.openstreetmap.de/routed-foot`; **car/auto/taxi route:** `router.project-osrm.org`. Both return OpenStreetMap-derived geometry, distance and duration. They are public, rate-limited/no-SLA services, not for high-volume deployment. On failure, no route, fare or ETA is invented. The separate local Dijkstra graph remains available independently. Basemap tiles are from OpenStreetMap with attribution.
- **Walking:** free; ETA is street distance at 4.5 km/h. **Auto-rickshaw:** approximate daytime meter ₹30 first 1.5 km + ₹11/km after. **Taxi:** *black/yellow non-AC metered taxi only*, approximate daytime meter ₹40 first 1 km + ₹17/km after. See [Delhi Transport's 2023 fare order](https://transport.delhi.gov.in/sites/default/files/Transport/circulars-orders/output.pdf). Auto/taxi ETA is OSRM driving duration + assumed five-minute pickup; there is no live traffic. Night surcharge (+25% 11pm–5am), waiting, tolls and detours are excluded. These are not fare quotes or ride-hailing prices; current tariffs should be checked before travel.
- **Metro and bus:** no station/stop matching, line routing, schedules or fare integration. A road distance is never used as a transit fare proxy. Both show no route/fare/ETA; check [DMRC](https://delhimetrorail.com/fare) and Delhi bus information for the actual journey. This does not imply service is unavailable.
- Four campus records are linked to verified OSM objects (Hindu, Miranda, St. Stephen's, DSE), using **polygon centroids, not gates**. The remaining eight curated place pins are approximate and not claimed to be OSM-verified. Check actual access on the ground. OSM data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL.

## Real OSM data and internet access

Leaflet 1.9.4 and OpenStreetMap basemap tiles require internet. Routing streets come from Overpass, independently of map tiles. The successful response is cached in `data/osm-cache.json`. Once cached, routing works without another Overpass download; map tiles and the Leaflet CDN still need internet. **Load streets** refreshes an already loaded OSM graph.

The Overpass servers were unavailable or timed out during this integration, so no live Delhi graph extract is bundled or claimed as verified. **This does not affect the default public OSRM trip mode**, which was exercised successfully. The optional Dijkstra graph downloader remains implemented. If its request fails on your computer:

1. Open [Overpass Turbo](https://overpass-turbo.eu/).
2. Paste and run:

```text
[out:json][timeout:35];
way["highway"](28.675,77.193,28.701,77.225);
(._;>;);
out body;
```

3. Export **raw data directly from Overpass API**, save the JSON, and choose **Import JSON** in Routebook. Use raw Overpass JSON, not GeoJSON.

This rectangle includes North Campus and nearby destinations. A route outside the extract may be shorter than the best route inside it: shortest-path claims apply to the loaded graph.

## Offline classroom demonstration

Choose **Sample graph · offline**. It contains 12 landmark vertices and 16 undirected connections (stored as 32 directed edges). Coordinates are approximate landmark pins; weights are invented teaching values, not measured road distances. The UI labels the graph and route accordingly. It is for explaining Dijkstra, never for navigation. If Leaflet cannot load, the algorithm tables and exports still work.

Example: Vishwavidyalaya Metro → Kamla Nagar Market gives `A → H → B → E → F → K`, total **2,280 m** in the sample graph. At the e-rickshaw sample settings, fare = `20 + (2.28 − 1) × 10 = ₹32.80`.

## Graph and routing model

- **Vertices:** every retained OSM street node; IDs are OSM IDs. Intermediate geometry points are retained so edge lengths follow the way geometry.
- **Edges:** each consecutive pair of allowed way nodes, directed according to one-way/access tags. Two-way segments contribute two edges.
- **Weight:** Haversine distance in metres. The algorithm uses full precision; UI values are rounded.
- **Dijkstra:** handwritten in `routing.py`, using `heapq`, adjacency lists, stale-entry skipping, and a predecessor map. No external routing engine computes the route.
- **Walking:** walkable streets/paths and pedestrian access tags; vehicle one-way rules do not constrain walking, but `oneway:foot` does.
- **Paid modes:** a basic motor-vehicle profile respects vehicle access, one-way streets, and roundabouts. E-rickshaw and auto share this profile. It does not encode all local vehicle restrictions or turn restrictions.
- **Landmark access:** curated pins are approximate, not verified gate coordinates. They snap to the nearest eligible street node, with a 450 m limit. Dashed access gaps are not navigable paths and are excluded from distance/time/fare. If the snapped nodes are disconnected, the app reports no route rather than inventing a connection.
- **Fare:** `base + max(0, distance_km − included_km) × extra_rate`. Walking and zero-distance routes cost zero. Example rates are editable classroom assumptions, **not official tariffs or live quotes**.
- **Time:** distance / assumed speed (walk 4.5 km/h; e-rickshaw 12; auto 18). No traffic, queues, stops, or access-gap time.

This finds the shortest **single-source to single-destination** street route. It is not a multi-stop tour optimiser. Campus access, opening times, gates, and safe pedestrian crossings need local verification.

## Project files

| File | Purpose |
| --- | --- |
| `app.py` | Local Python HTTP server, OSM download/import/cache, local Dijkstra and public trip APIs |
| `trip.py` | Public foot/car OSRM request parsing and conservative fare/time estimates |
| `routing.py` | Graph, Haversine weights, OSM profiles, Dijkstra, snapping, educational fare |
| `destinations.py` | Twelve named destinations with approximate pins |
| `static/` | HTML/CSS/JavaScript interface and Leaflet map |
| `tests/test_routing.py` | Algorithm correctness, profiles, fare, validation tests |
| `tests/test_trip.py` | Public endpoint, geometry, metered fares, transit and outage tests |
| `docs/PROJECT.md` | Mathematical explanation and viva preparation |

## Verification

```sh
python -m unittest discover -s tests -v
```

The tests compare Dijkstra with an independent Bellman–Ford implementation on seeded random graphs, as well as testing early termination, unreachable nodes, one-way/access behaviour, snapping, fare boundaries, and invalid imports. OSM parser tests use explicitly synthetic OSM-format fixtures.

## Sources and attribution

- [OpenStreetMap contributors / ODbL](https://www.openstreetmap.org/copyright) — map data and basemap attribution.
- [Overpass API by Example](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_API_by_Example) — street-data query.
- [OSM one-way documentation](https://wiki.openstreetmap.org/wiki/Key:oneway) — direction model.
- [Leaflet documentation](https://leafletjs.com/reference.html) — map rendering.
- [Python heapq documentation](https://docs.python.org/3/library/heapq.html) — priority queue.
- [University of Delhi campus map](https://www.du.ac.in/du/uploads/amenities/conference%20centre/DU_Map.pdf) — campus landmark context. Curated coordinates are approximate and not sourced from a surveyed gate dataset.

This is a local Python application; no hosted deployment or third-party API key is required.
