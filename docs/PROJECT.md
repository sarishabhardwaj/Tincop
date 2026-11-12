# Shortest Path and Fare Estimation for DU North Campus

## Aim

Model campus streets and bus/metro services as weighted graphs and use Dijkstra's algorithm to find a minimum-distance route. Show how the graph relates to a real OpenStreetMap basemap, then estimate a fare from the computed distance.

## Mathematical model

Let `G = (V, E)` be a directed graph. For walking, each street point is a vertex and an allowed consecutive OSM way segment is an edge. Two-way segments have edges in both directions. For bus/metro, vertices are mapped stops and edges are directed service connections between consecutive stops, reconstructed over available route-member geometry. For edge `(u,v)`, let `w(u,v) ≥ 0` be its cost: metres for walking or estimated minutes for bus/metro.

For walking, edge weights are metres and `L(P) = Σ w(u,v)` is minimised. For bus/metro, a virtual origin connects to stop vertices with mapped walking access, then a pre-boarding layer connects to a riding layer through an actual service edge. A virtual target connects through another mapped walking access path. This forces at least one ride. Edge weights are estimated minutes, so Dijkstra minimises the complete journey time within the selected mode. A 4 minute bus or 5 minute metro boarding allowance is included. The displayed route distance sums walking and riding metres; fare uses riding metres only.

The Haversine formula converts latitude/longitude into a great-circle segment length. OSM way geometry is represented by successive nodes, so a curved road contributes multiple short segments instead of one straight landmark-to-landmark line.

## Algorithm

```text
distance[source] = 0; all other distances = infinity
push (0, source) into the min-priority queue
while the queue is not empty:
    extract (distance_u, u) with smallest distance
    skip stale entries or already settled vertices
    settle u
    if u is the target: stop
    for each outgoing edge (u, v):
        candidate = distance_u + weight(u, v)
        if v is unsettled and candidate < distance[v]:
            distance[v] = candidate
            predecessor[v] = u
            push (candidate, v)
reconstruct target → predecessor → … → source, then reverse
```

**Relaxation:** `d(v) ← min(d(v), d(u) + w(u,v))`.

**Why this works:** when the minimum tentative vertex `u` is settled, no remaining route through an unsettled vertex can improve its distance. Any such route has a prefix at least as large as `d(u)` and cannot become smaller by adding non-negative weights. Thus each settled distance is final. A target must be settled, not merely discovered, before stopping.

The implementation returns tentative and settled cost records separately (metres for walking, minutes for bus/metro). Distances for unsettled vertices at early termination are not claimed to be final. A missing tentative distance means infinity.

**Complexity:** adjacency lists occupy `O(V + E)` memory. Python's heap uses repeated insertions instead of decrease-key, with at most `O(E)` successful relaxations and queue entries. Time is `O((V + E) log E)` and space is `O(V + E)`. For simple graphs this is commonly written `O((V + E) log V)`.

## Small example to present

Use the sample graph with Metro as source and Kamla Nagar as destination.

| Letter | Landmark |
| --- | --- |
| A | Vishwavidyalaya Metro |
| B | Arts Faculty |
| C | Kamla Nehru Ridge |
| D | Flagstaff Tower |
| E | Viceregal Lodge |
| F | Hindu College |
| G | St. Stephen's College |
| H | Miranda House |
| I | Shri Ram College of Commerce |
| J | Delhi School of Economics |
| K | Kamla Nagar Market |
| L | Hudson Lane |

The minimum path is `A → H → B → E → F → K` with weights `450 + 400 + 180 + 300 + 950 = 2,280 m`. These are invented classroom weights. They illustrate graph optimisation, not real travel distances.

On this sample distance, an ordinary bus ticket estimate is ₹5, AC bus ₹10, metro ₹21 and walking free. These demonstrate reference distance slabs, not actual services on the invented sample graph. The algorithm minimises distance first; ticket estimation is post-processing. A bus service change adds another ticket.

## Five-minute demonstration

1. Show the real campus map and select two landmarks.
2. Load/import OSM streets and enable **Show graph**. Explain street nodes versus landmark pins.
3. Find a walking route. Identify the distance and route polyline.
4. Open **Vertices & edges** to show directed edges and their weights.
5. Reset the trace and step through extract-min and relaxation. Explain infinity and the predecessor relationship.
6. Switch to Bus or Metro. Explain that these graphs require explicit service relations and stops; an ordinary road is not evidence of a service. The app reports missing transit data instead of inventing a route.
7. Compare ordinary/AC bus ticket estimates and metro reference slabs. Export the route's full trace as JSON.

For a road-routing demonstration without another data request, choose **Saved roads · offline** after one real OSM download/import. If no real data is available, **Maths diagram · offline** shows a separate abstract SVG graph. The synthetic example never returns geographic geometry or draws on the campus map.

## Viva questions

**Why Dijkstra instead of BFS?** BFS minimises edge count in an unweighted/equal-weight graph. Campus segments have different lengths; Dijkstra minimises their total weight.

**Why can it not handle negative weights?** A later route with a negative edge could improve a distance after the vertex is settled. The non-negative-weight invariant would fail.

**Why not use A*?** A* could speed up a geographic search with an admissible heuristic, but this project deliberately demonstrates Dijkstra without a heuristic.

**Is the shortest route always the cheapest?** Not generally. Not necessarily even within one mode: bus transfers can add tickets, and official fares can use fare stages or different network distances. Walking minimises mapped distance; bus/metro minimise estimated time before ticket estimation. Cheapest-fare optimisation or combined bus + metro + walking journeys need another graph/state model.

**Are landmarks the routing vertices?** Walking vertices are street nodes; bus/metro vertices are stops. Landmark pins select nearby eligible vertices. Access gaps are reported as numbers and are not drawn or treated as navigable links. The small sample graph treats landmark letters as vertices for teaching.

**What if there is no path?** The queue becomes empty before the target is settled. The app reports an unreachable route. It does not draw a fabricated street connection.

**Does a map itself calculate routes?** No. OSM tiles provide the visual background. The main OpenStreetMap API or a streets-only Overpass query supplies the street data; the Python implementation constructs and searches its own graph.

**What assumptions limit this project?** Approximate destination pins, a bounded street extract, incomplete OSM service coverage, bounded stop access, simple access rules, no turn restrictions or live schedules, and reference fare/speed assumptions. Bus/metro connections are reconstructed from ordered stops and connected route geometry. Access walks are routed along mapped streets; platform projection gaps are not routed. Unrouted access gaps are excluded from route totals and from the map polylines. Campuses and heritage sites can restrict entry.

## Data-download recovery

The main OSM map API is the first source, with a lightweight streets-only Overpass fallback. Python attempts these sources; the browser attempts them if Python cannot connect. Transit queries run separately. Imported `.osm` XML and OSM JSON are supported, and successful data is cached. Failed refreshes preserve a working cache. Saved roads mode performs no network download. The abstract maths example never replaces or masquerades as a real geographic route.

## Geometry regression check

A synthetic OSM test road has a right-angle bend. The test verifies that Dijkstra returns the intermediate corner node and that exported route segments preserve it. A frontend test checks the actual polyline calls: only the mapped segments are drawn, with no diagonal shortcut and no straight connection from off-road landmark pins. Another test checks that the maths demo creates zero map polylines.
