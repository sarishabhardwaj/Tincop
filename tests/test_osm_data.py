from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import app
from osm_data import MAP_URL, QUERY, decode_osm, merge_payloads
from routing import graph_from_osm


XML = '''<osm version="0.6">
<node id="1" lat="28.6943" lon="77.2149"/>
<node id="2" lat="28.6943" lon="77.2100"/>
<node id="3" lat="28.6894" lon="77.2100"/>
<way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/>
<tag k="highway" v="residential"/><tag k="name" v="L-shaped test road"/></way>
</osm>'''


class OSMDataTests(unittest.TestCase):
    def setUp(self):
        self.previous=dict(app.STATE)
        app.STATE.update(payload=None,graphs={},fetched_at=None)
        self.folder=tempfile.TemporaryDirectory()
        self.cache_patch=patch.object(app,'CACHE',Path(self.folder.name)/'cache.json')
        self.cache_patch.start()

    def tearDown(self):
        self.cache_patch.stop();self.folder.cleanup();app.STATE.update(self.previous)

    def test_official_xml_import_and_road_bends(self):
        payload=decode_osm(XML)
        app.install_osm(payload)
        result=app.route({'source':'osm','mode':'walk','start':'metro','end':'arts'})
        # Preserve the corner; never replace it with the diagonal 1→3.
        self.assertEqual(result['path'],['1','2','3'])
        self.assertEqual(result['geometry'],[[28.6943,77.2149],[28.6943,77.2100],[28.6894,77.2100]])
        self.assertEqual(result['segments'],[
            [[28.6943,77.2149],[28.6943,77.2100]],
            [[28.6943,77.2100],[28.6894,77.2100]]])
        self.assertGreater(result['distance_m'],1000)

    def test_main_osm_api_works_without_overpass(self):
        with patch('urllib.request.urlopen',return_value=BytesIO(XML.encode())) as download:
            app.load_osm()
        self.assertEqual(download.call_count,1)
        request=download.call_args.args[0]
        self.assertEqual(request.full_url,MAP_URL)
        self.assertEqual(request.get_method(),'GET')
        self.assertTrue(app.CACHE.exists())

    def test_overpass_fallback_is_streets_only(self):
        calls=[]
        def fetch(request,**kwargs):
            calls.append(request)
            if len(calls)==1:raise HTTPError(request.full_url,502,'Bad Gateway',{},None)
            return BytesIO(json.dumps(decode_osm(XML)).encode())
        with patch('urllib.request.urlopen',side_effect=fetch):app.load_osm()
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1].data.decode(),QUERY)
        self.assertNotIn('rel[',QUERY)

    def test_transit_merge_preserves_cached_streets(self):
        old=decode_osm(XML)
        merged=merge_payloads(old,{'elements':[{'type':'relation','id':50,'members':[],'tags':{'route':'bus'}}]})
        self.assertEqual(len(graph_from_osm(merged,'walk').edges),4)
        self.assertEqual(len(merged['elements']),5)

    def test_failed_refresh_preserves_real_cached_graph(self):
        app.install_osm(decode_osm(XML));app.save_cache(app.STATE['payload'])
        before=app.CACHE.read_bytes()
        graph=app.STATE['graphs']['walk']
        with patch('urllib.request.urlopen',side_effect=TimeoutError('provider timeout')):
            with self.assertRaisesRegex(ValueError,'could not download'):app.load_osm(force=True)
        self.assertIs(app.STATE['graphs']['walk'],graph)
        self.assertEqual(app.CACHE.read_bytes(),before)

    def test_saved_roads_route_bends_without_any_network_call(self):
        app.install_osm(decode_osm(XML));app.save_cache(app.STATE['payload'])
        app.STATE.update(payload=None,graphs={},fetched_at=None)
        with patch('urllib.request.urlopen',side_effect=AssertionError('Offline mode must not download')):
            result=app.route({'source':'cached','mode':'walk','start':'metro','end':'arts'})
        self.assertEqual(result['path'],['1','2','3'])
        self.assertEqual(result['geometry'][1],[28.6943,77.2100])
        self.assertEqual(result['coordinate_system'],'wgs84')

    def test_saved_roads_does_not_silently_use_synthetic_demo(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('No network in cache mode')):
            with self.assertRaisesRegex(ValueError,'No saved OSM streets'):
                app.get_graph('cached','walk')

    def test_reject_non_osm_xml_and_incomplete_json(self):
        with self.assertRaises(ValueError):decode_osm('<html>gateway error</html>')
        with self.assertRaises(ValueError):merge_payloads(decode_osm(XML),{'elements':[],'remark':'timed out'})


if __name__=='__main__':unittest.main()
