import unittest
from unittest.mock import patch

from trip import route_url, parse_osrm, estimate, plan_trip
from app import public_trip
from destinations import DESTINATIONS

A = {"id":"hindu","lat":28.6868,"lon":77.2093,"name":"Hindu College"}
B = {"id":"miranda","lat":28.6927,"lon":77.2101,"name":"Miranda House"}

class PublicTripTests(unittest.TestCase):
    def test_verified_landmarks_have_osm_record_references(self):
        places={p['id']:p for p in DESTINATIONS}
        self.assertEqual(places['hindu']['osm_ref'],'way/1266065702')
        self.assertEqual(places['miranda']['osm_ref'],'way/402853150')
        self.assertEqual(places['dse']['osm_ref'],'relation/19282541')

    def test_mode_endpoints_and_geometry(self):
        self.assertTrue(route_url(A,B,'walk').startswith('https://routing.openstreetmap.de/routed-foot/route/v1/driving/77.2093,28.6868;77.2101,28.6927'))
        self.assertTrue(route_url(A,B,'auto').startswith('https://router.project-osrm.org/route/v1/driving/'))
        result=parse_osrm({'code':'Ok','routes':[{'distance':1800,'duration':310,'geometry':{'coordinates':[[77.2093,28.6868],[77.2101,28.6927]]}}]})
        self.assertEqual(result['geometry'],[[28.6868,77.2093],[28.6927,77.2101]])
        with self.assertRaisesRegex(ValueError,'No street route'):parse_osrm({'code':'NoRoute','routes':[]})

    def test_official_metered_daytime_approximation_and_unknown_transit(self):
        self.assertEqual(estimate(1800,310,'auto')['fare'],33)
        self.assertEqual(estimate(1800,310,'taxi')['fare'],54)
        self.assertEqual(estimate(1400,310,'walk')['fare'],0)
        self.assertEqual(estimate(1400,310,'walk')['duration_minutes'],19)
        for mode in ('bus','metro'):
            result=plan_trip(A,B,mode)
            self.assertFalse(result['route_available'])
            self.assertIsNone(result['fare'])
            self.assertIsNone(result['duration_minutes'])
            self.assertEqual(result['geometry'],[])

    def test_api_uses_curated_places_and_rejects_unknown_ids(self):
        with patch('app.plan_trip',return_value={'route_available':False}) as planner:
            self.assertEqual(public_trip({'start':'hindu','end':'miranda','mode':'metro'}),{'route_available':False})
            self.assertEqual(planner.call_args.args[0]['id'],'hindu')
            with self.assertRaisesRegex(ValueError,'valid start'):public_trip({'start':'unknown','end':'miranda','mode':'walk'})

    def test_unavailable_osrm_does_not_invent_distance_or_fare(self):
        with patch('trip.fetch_osrm',side_effect=OSError('unavailable')):
            result=plan_trip(A,B,'auto')
        self.assertFalse(result['route_available'])
        self.assertIsNone(result['distance_m'])
        self.assertIsNone(result['fare'])
        self.assertEqual(result['geometry'],[])

if __name__=='__main__':unittest.main()
