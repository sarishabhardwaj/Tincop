# Shortest Path and Fare Estimation for DU North Campus

## Aim

Model campus streets as a weighted graph and use Dijkstra's algorithm to find a minimum-distance route. Show how the graph relates to a real OpenStreetMap basemap, then estimate a fare from the computed distance.

## Mathematical model

Let `G = (V, E)` be a directed graph. Each street point is a vertex, and an allowed consecutive segment of an OSM way is a directed edge. Two-way segments have edges in both directions. For edge `(u,v)`, let `w(u,v) ≥ 0` be the distance in metres.

For a path `P = (s, …, t)`, its length is `L(P) = Σ w(u,v)` over the edges in the path. We seek `P*` with minimum `L(P)` among paths from `s` to `t` in the loaded graph. Restricting graph size or access changes the set of candidate paths.

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

The implementation returns tentative and settled distance records separately. Distances for unsettled vertices at early termination are not claimed to be final. A missing tentative distance means infinity.

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

An e-rickshaw illustration uses a ₹20 base covering 1 km, then ₹10/km: `20 + max(0, 2.28 − 1) × 10 = ₹32.80`. Rates are editable. The algorithm minimises distance first; fare is a post-processing function.

## Five-minute demonstration

1. Show the real campus map and select two landmarks.
2. Load/import OSM streets and enable **Show graph**. Explain street nodes versus landmark pins.
3. Find a walking route. Identify the distance and route polyline.
4. Open **Vertices & edges** to show directed edges and their weights.
5. Reset the trace and step through extract-min and relaxation. Explain infinity and the predecessor relationship.
6. Switch to an auto or e-rickshaw profile. Explain that access/one-way rules can change the graph before the algorithm runs.
7. Edit fare assumptions and recalculate. Export the route's full trace as JSON.

If live OSM is unavailable, explicitly switch to **Sample graph** and explain that it is an educational model with invented edges. Do not describe it as an actual street route.

## Viva questions

**Why Dijkstra instead of BFS?** BFS minimises edge count in an unweighted/equal-weight graph. Campus segments have different lengths; Dijkstra minimises their total weight.

**Why can it not handle negative weights?** A later route with a negative edge could improve a distance after the vertex is settled. The non-negative-weight invariant would fail.

**Why not use A*?** A* could speed up a geographic search with an admissible heuristic, but this project deliberately demonstrates Dijkstra without a heuristic.

**Is the shortest route always the cheapest?** Not generally. With a common nondecreasing distance-based fare within one mode, it gives a minimum estimate under that formula. Different providers, tolls, waiting fees, traffic, or mixed-mode trips need another model.

**Are landmarks the routing vertices?** In the real OSM graph, the routing vertices are street nodes, and landmarks select nearby nodes. The small sample graph treats landmark letters as vertices for teaching.

**What if there is no path?** The queue becomes empty before the target is settled. The app reports an unreachable route. It does not draw a fabricated street connection.

**Does a map itself calculate routes?** No. OSM tiles provide the visual background. Overpass supplies the street data; the Python implementation constructs and searches its own graph.

**What assumptions limit this project?** Approximate destination pins, a bounded street extract, simple mode/access rules, no turn restrictions or live traffic, and illustrative fare/speed assumptions. Dashed snapping gaps are excluded from route totals. Campuses and heritage sites can restrict entry.
