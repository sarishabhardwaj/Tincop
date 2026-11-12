import math
import random
import unittest

from app import SAMPLE, STATE, install_osm, route
from routing import Graph, dijkstra, fare, graph_from_osm, haversine, nearest_node


def osm_fixture(tags=None, middle_tags=None):
    """Synthetic OSM-format fixture, not actual Delhi map data."""
    return {"elements": [
        {"type":"node","id":1,"lat":28.69,"lon":77.21},
        {"type":"node","id":2,"lat":28.691,"lon":77.21,"tags":middle_tags or {}},
        {"type":"node","id":3,"lat":28.692,"lon":77.21},
        {"type":"way","id":10,"nodes":[1,2,3],"tags":tags or {"highway":"residential"}},
    ]}


class RoutingTests(unittest.TestCase):
    def graph(self):
        graph=Graph()
        for n in 'ABCD':graph.add_node(n,0,0)
        for u,v,w in [('A','B',10),('A','C',1),('C','B',1),('B','D',1),('C','D',20)]:
            graph.add_edge(u,v,w)
        return graph

    def test_destination_is_not_final_when_first_discovered(self):
        result=dijkstra(self.graph(),'A','D')
        self.assertEqual(result['path'],['A','C','B','D'])
        self.assertEqual(result['distance_m'],3)
        self.assertEqual([s['node'] for s in result['steps']],['A','C','B','D'])

    def test_unreachable_and_identical_endpoints(self):
        graph=self.graph()
        with self.assertRaisesRegex(ValueError,'No connected route'):dijkstra(graph,'D','A')
        result=dijkstra(graph,'A','A')
        self.assertEqual(result['distance_m'],0)
        self.assertEqual(result['path'],['A'])
        self.assertEqual(result['edges'],[])

    def test_reject_invalid_weights(self):
        for weight in [-1,math.inf,math.nan]:
            with self.assertRaises(ValueError):self.graph().add_edge('A','B',weight)

    def test_against_independent_bellman_ford(self):
        rng=random.Random(12)
        for _ in range(20):
            graph=Graph()
            for i in range(12):graph.add_node(str(i),0,0)
            for u in graph.nodes:
                for v in graph.nodes:
                    if u!=v and rng.random()<.22:graph.add_edge(u,v,rng.randrange(0,30))
            expected={n:math.inf for n in graph.nodes};expected['0']=0
            for _ in range(11):
                for e in graph.edges:expected[e['v']]=min(expected[e['v']],expected[e['u']]+e['weight'])
            for target,distance in expected.items():
                if math.isinf(distance):
                    with self.assertRaises(ValueError):dijkstra(graph,'0',target)
                else:self.assertEqual(dijkstra(graph,'0',target)['distance_m'],distance)

    def test_osm_vehicle_oneway_and_walking(self):
        payload=osm_fixture({'highway':'residential','oneway':'yes'})
        self.assertEqual(len(graph_from_osm(payload,'walk').edges),4)
        driving=graph_from_osm(payload,'drive')
        self.assertEqual(len(driving.edges),2)
        self.assertGreater(dijkstra(driving,'1','3')['distance_m'],200)
        with self.assertRaises(ValueError):dijkstra(driving,'3','1')

    def test_reverse_oneway(self):
        graph=graph_from_osm(osm_fixture({'highway':'residential','oneway':'-1'}),'drive')
        self.assertEqual(dijkstra(graph,'3','1')['path'],['3','2','1'])
        with self.assertRaises(ValueError):dijkstra(graph,'1','3')

    def test_foot_specific_oneway(self):
        graph=graph_from_osm(osm_fixture({'highway':'footway','oneway:foot':'yes'}),'walk')
        with self.assertRaises(ValueError):dijkstra(graph,'3','1')

    def test_access_restrictions_and_specific_override(self):
        with self.assertRaises(ValueError):graph_from_osm(osm_fixture({'highway':'residential','access':'private'}),'walk')
        payload=osm_fixture({'highway':'residential','access':'private','foot':'yes'})
        self.assertEqual(len(graph_from_osm(payload,'walk').edges),4)
        with self.assertRaises(ValueError):graph_from_osm(payload,'drive')
        with self.assertRaises(ValueError):graph_from_osm(osm_fixture(middle_tags={'access':'no'}),'drive')

    def test_footways_not_used_by_vehicles(self):
        with self.assertRaises(ValueError):graph_from_osm(osm_fixture({'highway':'footway'}),'drive')

    def test_haversine_and_snap_limit(self):
        self.assertEqual(haversine([28,77],[28,77]),0)
        self.assertAlmostEqual(haversine([0,0],[0,1]),111195.08,places=1)
        graph=graph_from_osm(osm_fixture(),'walk')
        key,gap=nearest_node(graph,[28.69,77.21],True)
        self.assertEqual((key,gap),('1',0))
        with self.assertRaisesRegex(ValueError,'450'):nearest_node(graph,[0,0])

    def test_fare_boundaries(self):
        self.assertEqual(fare(2280,'erickshaw',20,10,1),32.8)
        self.assertEqual(fare(500,'erickshaw',20,10,1),20)
        self.assertEqual(fare(0,'auto',30,12,1),0)
        self.assertEqual(fare(3000,'walk'),0)
        with self.assertRaises(ValueError):fare(1000,'auto',math.nan)

    def test_sample_route_and_full_path_sum(self):
        result=route({'source':'sample','mode':'erickshaw','start':'metro','end':'kamla'})
        self.assertEqual(result['path'],['A','H','B','E','F','K'])
        self.assertEqual(result['distance_m'],2280)
        self.assertEqual(sum(e['weight'] for e in result['edges']),result['distance_m'])
        self.assertEqual(result['fare'],32.8)
        self.assertEqual(len(SAMPLE.nodes),12)

    def test_invalid_route_inputs(self):
        for body in [dict(source='wrong'),dict(source='sample',mode='bus'),dict(source='sample',start='unknown')]:
            with self.assertRaises(ValueError):route(body)
        with self.assertRaises(ValueError):route({'source':'sample','start':'metro','end':'kamla','fare':{'base':float('nan')}})

    def test_import_rejected_without_replacing_valid_state(self):
        previous=dict(STATE)
        try:
            install_osm(osm_fixture())
            current=STATE['payload']
            with self.assertRaises(ValueError):install_osm({'elements':[]})
            self.assertIs(STATE['payload'],current)
        finally:STATE.update(previous)


if __name__=='__main__':unittest.main()
