"""Optional public OSRM trip estimates; independent from the local Dijkstra lab."""
import json
import urllib.request

FOOT = 'https://routing.openstreetmap.de/routed-foot/route/v1/driving'
CAR = 'https://router.project-osrm.org/route/v1/driving'
FARE_SOURCE = 'https://transport.delhi.gov.in/sites/default/files/Transport/circulars-orders/output.pdf'


def route_url(start, end, mode):
    base = FOOT if mode == 'walk' else CAR
    return f'{base}/{start["lon"]},{start["lat"]};{end["lon"]},{end["lat"]}?overview=full&geometries=geojson'


def parse_osrm(payload):
    routes = payload.get('routes') or []
    if payload.get('code') != 'Ok' or not routes:
        raise ValueError('No street route returned by OSRM.')
    route = routes[0]
    coords = route.get('geometry', {}).get('coordinates') or []
    if len(coords) < 2 or route.get('distance') is None or route.get('duration') is None:
        raise ValueError('No street route geometry returned by OSRM.')
    return {'distance_m':route['distance'], 'osrm_seconds':route['duration'],
            'geometry':[[lat, lon] for lon, lat in coords]}


def fetch_osrm(start, end, mode):
    request = urllib.request.Request(route_url(start,end,mode), headers={'User-Agent':'Tinkop-NorthCampus/1.0 (student trip planner)'})
    with urllib.request.urlopen(request,timeout=15) as response:
        return parse_osrm(json.load(response))


def estimate(distance_m, seconds, mode):
    km = distance_m / 1000
    if mode == 'walk':
        return {'fare':0, 'duration_minutes':max(1,round(km/4.5*60)),
                'assumptions':'Walking at 4.5 km/h over OSRM foot route; no live ETA.'}
    if mode == 'auto':
        return {'fare':round(30+max(0,km-1.5)*11), 'duration_minutes':max(1,round(seconds/60+5)),
                'assumptions':'Approximate daytime auto meter: ₹30 first 1.5 km + ₹11/km after (Delhi Transport 2023); 5 min pickup assumption. Not a quote. Night +25%, waiting and detours excluded.'}
    if mode == 'taxi':
        return {'fare':round(40+max(0,km-1)*17), 'duration_minutes':max(1,round(seconds/60+5)),
                'assumptions':'Approximate daytime non-AC black/yellow metered taxi: ₹40 first km + ₹17/km after (Delhi Transport 2023); 5 min pickup assumption. Not ride-hailing. Night +25%, waiting and detours excluded.'}
    raise ValueError('Unsupported street trip mode.')


def plan_trip(start,end,mode):
    if mode not in ('walk','auto','taxi','metro','bus'):
        raise ValueError('Unknown trip mode.')
    base = {'source':'public','mode':mode,'start':start,'end':end,'route_available':False,
            'geometry':[],'distance_m':None,'duration_minutes':None,'fare':None,'fare_source':FARE_SOURCE}
    if mode in ('metro','bus'):
        return {**base,'message':f'No verified {mode} line/stop route, fare or timetable. Check the operator before travelling.',
                'assumptions':'Road distance cannot establish a transit fare or travel time.'}
    try:
        route = fetch_osrm(start,end,mode)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {**base,'message':f'Street routing unavailable ({error}). No fare or ETA calculated.',
                'assumptions':'Public OSRM can be slow or rate-limited. No straight line is treated as a route.'}
    return {**base,**route,**estimate(route['distance_m'],route['osrm_seconds'],mode),
            'route_available':True,'message':'OSRM OpenStreetMap street geometry; approximate time and fares, not a live quote.'}
