# North Campus Routebook

A Python Discrete Mathematics project for shortest routes around Delhi University North Campus, using **Dijkstra's algorithm**, OpenStreetMap and **Walking / Bus / Metro**.

## Run

Requires **Python 3.10+**. No pip packages or API keys are needed.

```sh
python app.py
```

Open **http://127.0.0.1:8000**. On Windows, `py app.py` also works. Use `python app.py --port 8080` if port 8000 is occupied. After updating Python files, stop the existing server with Ctrl+C, restart it, and refresh your browser.

1. Choose two destinations and Walking, Bus, or Metro.
2. Click **Find shortest route**, or **Load network** first.
3. View the route, distance, estimated travel time, and ticket estimate.
4. Step through **Dijkstra's trace** or inspect **Vertices & edges**.
5. Export the full algorithm trace as JSON or graph edges as CSV.

The interface is a restrained campus field guide with a large map. Python computes the routes; JavaScript manages the interface and Leaflet map.

## Street downloads and offline road routing

The app requests a small campus extract from the **main OpenStreetMap map API**, independently of Overpass. Its fallback is a small **streets-only** Overpass query. Python attempts these sources first; the browser tries them if Python cannot connect. Bus/metro service data is requested separately only when needed. A slow transit query cannot block the walking street download.

Requests are bounded and there is a **Cancel download** button. Failed downloads preserve a working cache, and incomplete Overpass responses are rejected. External API uptime and network access still cannot be guaranteed.

To import without using Overpass:

1. Open **? → Download OSM file** in the app, or [download the campus OSM export](https://api.openstreetmap.org/api/0.6/map?bbox=77.199,28.679,77.224,28.700).
2. Save the XML response as `north-campus.osm`.
3. Choose **Import OSM** and select the file. Both `.osm` / XML and OSM-format JSON are supported; GeoJSON is not.
4. For later demonstrations, choose **Saved roads · offline**. This reads the real saved graph and never attempts a network download. It retains road bends and connectivity. It requires one successful real download/import; no fake road dataset is bundled.

Successful data is cached in `data/osm-cache.json`. Offline graph computation works without Overpass or the OSM API, but the Leaflet CDN and basemap tiles still require internet or existing browser caches.

The alternate streets-only query is:

```text
[out:json][timeout:15];way["highway"](28.679,77.199,28.700,77.224);(._;>;);out body;
```

The separate transit supplement is:

```text
[out:json][timeout:25];rel["type"="route"]["route"~"^(bus|subway)$"](28.679,77.199,28.700,77.224)->.services;way(r.services)(28.679,77.199,28.700,77.224)->.ways;node(r.services)(28.679,77.199,28.700,77.224)->.stops;(.services;.ways;.stops;node(w.ways););out body;
```

Transit geometry outside the bounding rectangle is excluded. Shortest-path claims apply to the loaded graph, since a route leaving the extract might be shorter.

## Transport model

| Mode | Graph | Fare estimate |
| --- | --- | --- |
| Walking | Allowed street/footpath nodes and consecutive way segments | Free |
| Bus | Ordered stops in explicit OSM bus route relations; directed connections use available road geometry | Ordinary or AC distance slabs; new ticket when service changes |
| Metro | Ordered stops in explicit OSM subway route relations; connections use available track geometry | Reference standard-distance slabs |

Bus and metro services are **never inferred from a generic road network**. Missing or disconnected transit services produce a clear message. OSM coverage may be incomplete: absence of a usable service in this extract does not establish that no real service exists. The app does not provide live departures.

Transit connections are reconstructed between consecutive mapped stops over connected member ways. Bus geometry respects road one-way/access rules. Subway direction comes from the stop order of each route relation; a reverse service needs its own relation. Stop/platform pairs at the same position are deduplicated. Platforms represented only by polygons are not currently supported.

Pins are approximate landmark locations, not verified entrances. Walking snaps to street nodes within 450 m; transit snaps to stops within 1,500 m. Access gaps are reported numerically, **never drawn as roads or walking paths**, and excluded from distance, time and fare. The map marks where the actual network route starts and ends. The app searches between the nearest selected vertices; it does not compare all alternative access stops. If two landmarks snap to the same station, there is no metro ride and the fare is zero; use Walking for that local journey.

This version compares separate walking, bus and metro graphs. It does **not** optimise a combined bus + metro + walking itinerary, schedules, turn restrictions, transfer walks, opening hours or traffic. Platform-to-track snapping is an approximation; tiny projection gaps are not added to ride distance. Check campus entry rules locally.

## Ticket reference

Fares are estimated after the algorithm minimises distance. They are not live quotes, fare-stage lookups or concessions.

- Ordinary bus: up to 4 km ₹5; above 4–10 km ₹10; above 10 km ₹15.
- AC bus: up to 4 km ₹10; above 4–8 km ₹15; above 8–12 km ₹20; above 12 km ₹25.
- Metro standard reference: up to 2 / 5 / 12 / 21 / 32 / over 32 km: ₹11 / ₹21 / ₹32 / ₹43 / ₹54 / ₹64.
- Metro discounts, Sunday/holiday concessions and other fare exceptions are excluded. A service change on a bus adds another ticket estimate; metro line changes use one total-distance estimate.
- Travel time uses assumed speeds: walking 4.5 km/h, bus 15 km/h and metro 32 km/h. Waiting, access and boarding time are excluded.

References: [Delhi Tourism bus fares](https://delhitourism.gov.in/transport/city_bus.html), [DMRC fare page](https://delhimetrorail.com/fare). Confirm the actual ticket fare before travel.

## Offline presentation

For actual road routing, choose **Saved roads · offline** after downloading/importing once. The Python algorithm searches the real saved OSM street graph, and the map uses the same consecutive way segments as the route. No direct landmark-to-landmark lines are created. If saved streets are unavailable, this mode reports that fact instead of substituting a synthetic network.

For an algorithm-only illustration, choose **Maths diagram · offline**. It shows a separate SVG diagram containing 12 vertices and 16 undirected connections (32 directed edges) with invented weights. Its coordinates are diagram layout units, not latitude/longitude. The sample API returns **no geographic route geometry**, and the frontend never draws its connections on the campus map.

Sample example: `A → H → B → E → F → K`, total 2,280 m. The ordinary-bus illustration is ₹5, AC ₹10, metro ₹21 and walking free. These do not represent actual services. The abstract diagram, algorithm tables and exports work without Leaflet.

## Road geometry guarantee

Every walking edge retains its two consecutive OSM way nodes. Bus/metro edges retain the complete reconstructed road/track polyline between stops. A route with missing geographic geometry is rejected instead of replaced with a straight chord. Disconnected edges are drawn as separate segments, with no artificial line bridging gaps. Landmark access gaps are never added as map polylines.

## Files and checks

| File | Purpose |
| --- | --- |
| `app.py` | Local HTTP server, downloading/importing/caching and route API |
| `routing.py` | Weighted graph, Haversine weights, street access and Dijkstra |
| `osm_data.py` | Main OSM API, separate street/transit queries, XML/JSON decoding and merging |
| `transit.py` | Stop-to-stop bus/metro graphs and ticket slabs |
| `destinations.py` | Twelve approximate landmark pins |
| `static/` | Map/interface and browser-side download fallback |
| `tests/` | Algorithm, HTTP, transit, fare and download-recovery checks |
| `docs/PROJECT.md` | Mathematical explanation and viva guide |

```sh
python -m unittest discover -s tests -v
node tests/test_download.cjs
```

Node is needed only for the JavaScript recovery tests, not to run the application. Python tests independently compare Dijkstra against Bellman–Ford and exercise synthetic OSM street/transit fixtures, XML imports, cached road routes and road-corner preservation. JavaScript tests simulate provider failures and cancellation, and check that the maths demo draws no geographic lines while real routes retain their bends without landmark connectors.

The development environment blocks external downloads and local server sockets. Tests run without either; a real Delhi map download, live server and browser appearance remain unverified here. No downloaded Delhi extract is bundled.

## Sources and attribution

- [OpenStreetMap contributors / ODbL](https://www.openstreetmap.org/copyright) — map data and basemap attribution.
- [OSM map download API](https://wiki.openstreetmap.org/wiki/API_v0.6#Retrieving_map_data_by_bounding_box:_GET_/api/0.6/map) — independent small-area export.
- [Overpass API by Example](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_API_by_Example) — map-data queries.
- [Leaflet documentation](https://leafletjs.com/reference.html) — map rendering.
- [Python heapq documentation](https://docs.python.org/3/library/heapq.html) — min-priority queue.
- [University of Delhi campus map](https://www.du.ac.in/du/uploads/amenities/conference%20centre/DU_Map.pdf) — campus context.
- Approximate pins were cross-checked where available with [Flagstaff Tower's geotagged photograph](https://commons.wikimedia.org/wiki/File:Flagstaff_Tower,_Delhi.jpg), [Hindu College on Mapcarta/OSM](https://mapcarta.com/W1266065702), [SRCC on Mapcarta/OSM](https://mapcarta.com/W818318820), [DSE's alumni directory](https://wiki.alumni.net/wiki/Asia/India/Delhi/New_Delhi/University_of_Delhi_North_Campus/Delhi_School_of_Economics/), and [Viceregal Lodge's listing](https://india.worldplaces.me/view-place/40071146-vice-regal-lodge-delhi-university.html). These are not surveyed gate coordinates.
