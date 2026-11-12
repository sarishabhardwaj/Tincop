"""Build stop-to-stop transit edges only from explicit OSM route relations."""
import math
from routing import Graph, dijkstra, graph_from_osm, haversine, largest_component, nearest_node, shortest_tree, tree_path


def transit_graph(payload, mode):
    elements=payload['elements']
    nodes={e['id']:e for e in elements if e['type']=='node'}
    ways={e['id']:e for e in elements if e['type']=='way'}
    graph=Graph()
    for relation in elements:
        if relation['type']!='relation' or relation.get('tags',{}).get('route') != ('subway' if mode=='metro' else 'bus'):
            continue
        members=relation.get('members',[])
        route_ways=[ways[m['ref']] for m in members if m['type']=='way' and m['ref'] in ways and m.get('role','') not in {'platform','platform_entry_only','platform_exit_only'}]
        # Only geometry actually included in the extract can form a connection.
        if not route_ways:
            continue
        if mode=='metro':
            network=Graph()
            for way in route_ways:
                if way.get('tags',{}).get('railway') not in {'subway','rail','light_rail'}:
                    continue
                for a,b in zip(way.get('nodes',[]),way.get('nodes',[])[1:]):
                    if a not in nodes or b not in nodes:continue
                    for key in (a,b):
                        n=nodes[key];network.add_node(key,n['lat'],n['lon'])
                    w=haversine(network.nodes[str(a)],network.nodes[str(b)])
                    network.add_edge(a,b,w);network.add_edge(b,a,w)
        else:
            try:network=graph_from_osm({'elements':list(nodes.values())+route_ways},'bus')
            except ValueError:continue
        if not network.edges:continue
        stops=[]
        for member in members:
            if member['type']!='node' or member['ref'] not in nodes:continue
            role=member.get('role','')
            if not (role.startswith('stop') or role.startswith('platform')):continue
            n=nodes[member['ref']];coord=[n['lat'],n['lon']]
            nearest=min(network.nodes,key=lambda key:haversine(coord,network.nodes[key]))
            if haversine(coord,network.nodes[nearest])>200:continue
            # PTv2 relations may list a stop position followed by its platform.
            if stops and (haversine(coord,stops[-1]['coord'])<90 or nearest==stops[-1]['road']):continue
            stops.append({'key':f"stop:{member['ref']}",'coord':coord,'road':nearest,
                          'name':n.get('tags',{}).get('name',f"Stop {member['ref']}"),'role':role})
        service=relation.get('tags',{}).get('ref',relation.get('tags',{}).get('name',str(relation['id'])))
        for a,b in zip(stops,stops[1:]):
            if a['role'].endswith('exit_only') or b['role'].endswith('entry_only'):continue
            try:path=dijkstra(network,a['road'],b['road'])
            except ValueError:continue
            if not path['edges']:continue
            for stop in (a,b):graph.add_node(stop['key'],*stop['coord'])
            graph.add_edge(a['key'],b['key'],path['distance_m'],f"{mode.title()} {service}: {a['name']} → {b['name']}",relation['id'])
            graph.edges[-1].update(geometry=[network.nodes[n] for n in path['path']],service=str(service),transport=mode)
    return graph


def transit_journey(streets, services, start, end, mode):
    """Find a service journey with mapped walking access at both ends.

    Two stop layers require at least one transit edge. Access edge weights
    are minutes, so Dijkstra chooses the fastest estimated complete journey.
    """
    connected = largest_component(streets)
    start_node, start_gap = nearest_node(streets, start, outgoing=True,allowed=connected)
    end_node, end_gap = nearest_node(streets, end,allowed=connected)
    from_start, forward = shortest_tree(streets, start_node)
    to_end, reverse = shortest_tree(streets, end_node, reverse=True)
    graph = Graph()
    graph.add_node('__origin__', *streets.nodes[start_node])
    graph.add_node('__target__', *streets.nodes[end_node])
    speed = 250 if mode == 'bus' else 32000 / 60  # metres per minute
    boarding_minutes = 4 if mode == 'bus' else 5
    stop_access = {}
    for key, point in services.nodes.items():
        # A stop must have a mapped street approach. Its unmapped platform
        # projection is disclosed, never drawn as a path through a building.
        try: road, gap = nearest_node(streets, point, max_distance=300,allowed=connected)
        except ValueError: continue
        stop_access[key] = (road, gap)
        for prefix in ('pre:', 'ride:'):
            graph.add_node(prefix+key, *point)
    for key, (road, gap) in stop_access.items():
        if road in from_start and from_start[road] <= 4000:
            edges = tree_path(forward, start_node, road)
            geometry = [streets.nodes[start_node]] + [streets.nodes[e['v']] for e in edges]
            distance = from_start[road]
            graph.add_edge('__origin__','pre:'+key,distance/75,'Walk to boarding stop')
            graph.edges[-1].update(geometry=geometry if len(geometry)>1 else geometry*2,
                                   distance_m=distance, transport='walk', stop_gap_m=gap)
        if road in to_end and to_end[road] <= 4000:
            edges = tree_path(reverse, road, end_node, reverse=True)
            geometry = [streets.nodes[road]] + [streets.nodes[e['v']] for e in edges]
            distance = to_end[road]
            graph.add_edge('ride:'+key,'__target__',distance/75,'Walk from alighting stop')
            graph.edges[-1].update(geometry=geometry if len(geometry)>1 else geometry*2,
                                   distance_m=distance, transport='walk', stop_gap_m=gap)
    for edge in services.edges:
        if edge['u'] not in stop_access or edge['v'] not in stop_access:
            continue
        ride_minutes = edge['weight']/speed
        for u, extra in (('pre:'+edge['u'],boarding_minutes),('ride:'+edge['u'],0)):
            graph.add_edge(u,'ride:'+edge['v'],ride_minutes+extra,edge['name'],edge['way_id'])
            graph.edges[-1].update(geometry=edge['geometry'],distance_m=edge['weight'],
                                   service=edge.get('service'),transport=mode)
    try:
        result = dijkstra(graph,'__origin__','__target__')
    except ValueError:
        raise ValueError(f'No connected {mode} journey with mapped walking access was found in this OSM extract. Try Walking or a different destination.') from None
    result.update(duration_minutes=result['distance_m'],
                  distance_m=sum(e['distance_m'] for e in result['edges']),
                  ride_distance_m=sum(e['distance_m'] for e in result['edges'] if e['transport']==mode),
                  access_distance_m=sum(e['distance_m'] for e in result['edges'] if e['transport']=='walk'),
                  stop_access_gap_m=sum(e.get('stop_gap_m',0) for e in result['edges']),
                  start_snap_m=start_gap,end_snap_m=end_gap,
                  trace_nodes=graph.nodes,cost_unit='min',optimality='estimated_time',
                  walking_alternative_minutes=from_start.get(end_node, math.inf)/75,
                  route_graph={'nodes':graph.nodes,'links':graph.edges,
                               'vertices':len(graph.nodes),'edges':len(graph.edges),'weight_unit':'min'},
                  graph_vertices=len(graph.nodes),graph_edges=len(graph.edges))
    return result


def transit_fare(distance_m, mode, ac=False):
    """Reference distance slabs, not live ticket quotes or concessions."""
    if not math.isfinite(distance_m) or distance_m < 0:
        raise ValueError('Distance must be finite and non-negative.')
    if mode not in {'walk','bus','metro'}:
        raise ValueError('Unknown transport mode.')
    if distance_m<=0 or mode=='walk':return 0
    km=distance_m/1000
    if mode=='bus':
        slabs=[(4,10),(8,15),(12,20),(float('inf'),25)] if ac else [(4,5),(10,10),(float('inf'),15)]
    elif mode=='metro':
        slabs=[(2,11),(5,21),(12,32),(21,43),(32,54),(float('inf'),64)]
    else:raise ValueError('Unknown transport mode.')
    return next(value for limit,value in slabs if km<=limit)
