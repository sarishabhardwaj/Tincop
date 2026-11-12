"""Synthetic transit fixtures: explicit services, stops, and way geometry."""
import unittest

from routing import dijkstra
from transit import transit_graph, transit_fare


def fixture(mode='bus', reverse=False, missing=False):
    nodes=[{'type':'node','id':i,'lat':28.69+i*.001,'lon':77.21,
            'tags':{'name':f'Stop {i}'}} for i in (1,2,3)]
    way={'type':'way','id':10,'nodes':[1,2,3],
         'tags':{'highway':'residential','oneway':'yes'} if mode=='bus' else {'railway':'subway'}}
    order=[3,2,1] if reverse else [1,2,3]
    relation={'type':'relation','id':100,'tags':{'type':'route','route':'bus' if mode=='bus' else 'subway','ref':'Test Line'},
              'members':[{'type':'node','ref':i,'role':'stop'} for i in order]+
                        [{'type':'way','ref':10,'role':''}]}
    return {'elements':nodes+([] if missing else [way])+[relation]}


class TransitTests(unittest.TestCase):
    def test_bus_follows_a_named_service(self):
        graph=transit_graph(fixture(),'bus')
        result=dijkstra(graph,'stop:1','stop:3')
        self.assertEqual(result['path'],['stop:1','stop:2','stop:3'])
        self.assertIn('Test Line',result['edges'][0]['name'])
        self.assertAlmostEqual(result['edges'][0]['geometry'][0][0],28.691)
        self.assertEqual(result['edges'][0]['geometry'][1],[28.692,77.21])
        with self.assertRaises(ValueError):dijkstra(graph,'stop:3','stop:1')

    def test_bus_does_not_ignore_oneway_geometry(self):
        self.assertFalse(transit_graph(fixture(reverse=True),'bus').edges)

    def test_subway_uses_tracks_not_streets(self):
        graph=transit_graph(fixture('metro'),'metro')
        self.assertEqual(dijkstra(graph,'stop:1','stop:3')['path'],['stop:1','stop:2','stop:3'])
        self.assertFalse(transit_graph(fixture('bus'),'metro').edges)

    def test_no_geometry_no_invented_transit_connections(self):
        self.assertFalse(transit_graph(fixture(missing=True),'bus').edges)
        self.assertFalse(transit_graph({'elements':fixture()['elements'][:-1]},'bus').edges)

    def test_reverse_metro_relation(self):
        graph=transit_graph(fixture('metro',reverse=True),'metro')
        self.assertEqual(dijkstra(graph,'stop:3','stop:1')['path'],['stop:3','stop:2','stop:1'])

    def test_all_ticket_slab_boundaries(self):
        for distance,ordinary,ac in [(4000,5,10),(4001,10,15),(8000,10,15),(8001,10,20),(10001,15,20),(12001,15,25)]:
            self.assertEqual(transit_fare(distance,'bus'),ordinary)
            self.assertEqual(transit_fare(distance,'bus',True),ac)
        for distance,expected in [(2000,11),(2001,21),(5001,32),(12001,43),(21001,54),(32001,64)]:
            self.assertEqual(transit_fare(distance,'metro'),expected)


if __name__=='__main__':unittest.main()
