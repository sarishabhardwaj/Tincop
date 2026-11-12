"""Small-area OSM downloads, independent of the Overpass query service."""
import json
import xml.etree.ElementTree as ET


BBOX = "28.679,77.199,28.700,77.224"
south, west, north, east = BBOX.split(',')
MAP_URL = f'https://api.openstreetmap.org/api/0.6/map.json?bbox={west},{south},{east},{north}'
EXPORT_URL = f'https://api.openstreetmap.org/api/0.6/map?bbox={west},{south},{east},{north}'
# Keep the walking download cheap. Do not make it wait for route relations.
QUERY = f'[out:json][timeout:15];way["highway"]({BBOX});(._;>;);out body;'
TRANSIT_QUERY = (
    f'[out:json][timeout:25];rel["type"="route"]["route"~"^(bus|subway)$"]({BBOX})->.services;'
    f'way(r.services)({BBOX})->.ways;node(r.services)({BBOX})->.stops;'
    '(.services;.ways;.stops;node(w.ways););out body;')
ENDPOINTS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']


def download_sources(transit=False):
    if transit:
        return [{"name":"Overpass transit", "url":endpoint, "query":TRANSIT_QUERY} for endpoint in ENDPOINTS]
    return [{"name":"OpenStreetMap map API", "url":MAP_URL},
            {"name":"Overpass streets", "url":ENDPOINTS[0], "query":QUERY}]


def decode_osm(data):
    """Accept official OSM XML exports and OSM/Overpass JSON."""
    if isinstance(data,dict):return data
    if not isinstance(data,(str,bytes)):
        raise ValueError('Import an OSM JSON or .osm XML file.')
    if not data.lstrip().startswith(b'<' if isinstance(data,bytes) else '<'):
        return json.loads(data)
    try:
        root=ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError(f'Invalid OSM XML: {error}') from None
    if root.tag!='osm':
        raise ValueError('Expected an OpenStreetMap .osm XML export.')
    elements=[]
    for item in root:
        if item.tag not in {'node','way','relation'}:continue
        element={'type':item.tag,'id':int(item.attrib['id'])}
        tags={child.attrib['k']:child.attrib['v'] for child in item.findall('tag')}
        if tags:element['tags']=tags
        if item.tag=='node':
            element.update(lat=float(item.attrib['lat']),lon=float(item.attrib['lon']))
        elif item.tag=='way':
            element['nodes']=[int(child.attrib['ref']) for child in item.findall('nd')]
        else:
            element['members']=[{'type':child.attrib['type'],'ref':int(child.attrib['ref']),
                                 'role':child.attrib.get('role','')} for child in item.findall('member')]
        elements.append(element)
    return {'elements':elements}


def merge_payloads(old,new):
    """Merge a transit supplement without losing cached walking streets."""
    if not isinstance(new,dict) or not isinstance(new.get('elements'),list):
        raise ValueError('Expected OSM elements.')
    if new.get('remark'):
        raise ValueError(f"Incomplete OSM response: {new['remark']}")
    index={(e['type'],e['id']):e for e in (old or {}).get('elements',[])}
    index.update({(e['type'],e['id']):e for e in new['elements']})
    return {'elements':list(index.values())}
