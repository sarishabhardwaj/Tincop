"""Build stop-to-stop transit edges only from explicit OSM route relations."""
import math
from routing import Graph, dijkstra, graph_from_osm, haversine


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
