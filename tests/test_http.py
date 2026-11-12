"""Exercise HTTP parsing and handlers without network/socket permissions."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app


def request(method, path, body=None, origin=None):
    content=json.dumps(body).encode() if body is not None else b''
    headers=f'{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:8000\r\nContent-Length: {len(content)}\r\n'
    if origin:headers+=f'Origin: {origin}\r\n'
    handler=app.Handler.__new__(app.Handler)
    handler.rfile=BytesIO(headers.encode()+b'\r\n'+content)
    handler.wfile=BytesIO()
    handler.client_address=('127.0.0.1',1234)
    handler.log_message=lambda *args: None
    handler.handle_one_request()
    head,data=handler.wfile.getvalue().split(b'\r\n\r\n',1)
    return int(head.split()[1]),data


class HTTPTests(unittest.TestCase):
    def test_static_assets_and_config(self):
        for path in ['/', '/app.js', '/style.css', '/api/config']:
            code,data=request('GET',path)
            self.assertEqual(code,200,path)
            self.assertTrue(data)
        code,data=request('GET','/api/config')
        self.assertEqual(len(json.loads(data)['destinations']),12)
        self.assertEqual(request('GET','/../../app.py')[0],404)

    def test_sample_api_all_modes_and_graph_export(self):
        for mode in ['walk','bus','metro']:
            code,data=request('POST','/api/route',{'source':'sample','mode':mode,'start':'metro','end':'kamla'})
            self.assertEqual(code,200)
            result=json.loads(data)
            self.assertEqual(result['distance_m'],2280)
            self.assertEqual(result['path'],['A','H','B','E','F','K'])
            self.assertEqual(result['geometry'],[])
            self.assertEqual(result['segments'],[])
            self.assertEqual(result['coordinate_system'],'diagram')
        code,data=request('POST','/api/graph',{'source':'sample'})
        self.assertEqual(code,200)
        self.assertEqual(json.loads(data)['edges'],32)

    def test_invalid_input_and_cross_origin(self):
        code,data=request('POST','/api/route',{'source':'sample','mode':'bus','start':'metro','end':'kamla','fare':{'bus_type':'invalid'}})
        self.assertEqual(code,400)
        self.assertIn('error',json.loads(data))
        self.assertEqual(request('POST','/api/route',[],None)[0],400)
        self.assertEqual(request('POST','/api/graph',{'source':'sample'},'https://example.com')[0],403)

    def test_osm_import_cache_and_route(self):
        # Synthetic coordinates match curated pins to isolate HTTP/OSM integration.
        payload={'elements':[
            {'type':'node','id':1,'lat':28.6943,'lon':77.2149},
            {'type':'node','id':2,'lat':28.692,'lon':77.212},
            {'type':'node','id':3,'lat':28.6894,'lon':77.2100},
            {'type':'way','id':99,'nodes':[1,2,3],
             'tags':{'highway':'residential','name':'Synthetic Test Road','oneway':'yes'}}]}
        previous=dict(app.STATE)
        try:
            with tempfile.TemporaryDirectory() as folder, patch.object(app,'CACHE',Path(folder)/'cache.json'):
                code,data=request('POST','/api/import',{'payload':payload,'mode':'walk'})
                self.assertEqual(code,200)
                self.assertTrue(app.CACHE.exists())
                code,data=request('POST','/api/route',{'source':'osm','mode':'walk','start':'metro','end':'arts'})
                self.assertEqual(code,200)
                route=json.loads(data)
                self.assertEqual(route['path'],['1','2','3'])
                self.assertEqual(route['start_snap_m'],0)
                self.assertGreater(route['distance_m'],600)
                reverse=request('POST','/api/route',{'source':'osm','mode':'walk','start':'arts','end':'metro'})
                self.assertEqual(reverse[0],200)
                app.STATE.update(payload=None,graphs={},fetched_at=None)
                with patch('urllib.request.urlopen',side_effect=AssertionError('Cache should avoid downloads')):
                    app.load_osm()
                self.assertEqual(len(app.STATE['graphs']['walk'].edges),4)
                # Street data must never be advertised as an actual bus service.
                self.assertEqual(request('POST','/api/route',{'source':'osm','mode':'bus','start':'metro','end':'arts'})[0],400)
        finally:app.STATE.update(previous)

    def test_transit_route_api_preserves_service_and_geometry(self):
        payload={'elements':[
            {'type':'node','id':1,'lat':28.6943,'lon':77.2149,'tags':{'name':'Start stop'}},
            {'type':'node','id':2,'lat':28.692,'lon':77.212},
            {'type':'node','id':3,'lat':28.6894,'lon':77.2100,'tags':{'name':'Arrival stop'}},
            {'type':'way','id':99,'nodes':[1,2,3],'tags':{'highway':'residential'}},
            {'type':'relation','id':100,'tags':{'type':'route','route':'bus','ref':'Synthetic Service'},
             'members':[{'type':'node','ref':1,'role':'stop'},{'type':'node','ref':3,'role':'stop'},
                        {'type':'way','ref':99,'role':''}]}]}
        previous=dict(app.STATE)
        try:
            app.install_osm(payload)
            code,data=request('POST','/api/route',{'source':'osm','mode':'bus','start':'metro','end':'arts'})
            self.assertEqual(code,200)
            result=json.loads(data)
            self.assertEqual(result['path'],['stop:1','stop:3'])
            self.assertEqual(len(result['geometry']),3)
            self.assertEqual(result['fare'],5)
            self.assertEqual(result['legs'][0]['service'],'Synthetic Service')
            self.assertEqual(len(result['segments']),1)
        finally:app.STATE.update(previous)


if __name__=='__main__':unittest.main()
