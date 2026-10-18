"""Offline regression tests: outage fallback, safe failures, settings restoration."""
import unittest
from unittest.mock import patch

import osmnx as ox
from requests.exceptions import ConnectionError

from nd_route_finder.geodata.overpass_fallback import OverpassFallback
from nd_route_finder.geodata.overpass_unavailable_error import OverpassUnavailableError


class OverpassFallbackTests(unittest.TestCase):
    def test_tries_another_server_after_502_then_restores_settings(self):
        previous = (ox.settings.overpass_url, ox.settings.overpass_rate_limit,
                    ox.settings.requests_timeout)
        seen = []
        statuses = []

        def operation():
            seen.append(ox.settings.overpass_url)
            if len(seen) == 1:
                raise ox._errors.ResponseStatusCodeError('HTTP 502 Bad Gateway')
            return 'success'

        with patch('nd_route_finder.geodata.overpass_fallback.time.sleep'):
            self.assertEqual(OverpassFallback().execute(operation, 'routing network', statuses.append),
                             'success')
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0], seen[1])
        self.assertEqual(previous, (ox.settings.overpass_url, ox.settings.overpass_rate_limit,
                                    ox.settings.requests_timeout))
        self.assertIn('switching', ' '.join(statuses))

    def test_504_does_not_trigger_osmnx_unbounded_recursive_retry(self):
        from collections import OrderedDict
        from types import SimpleNamespace

        # A real OSMnx 504 normally sleeps 55 seconds and recursively retries.
        with patch('nd_route_finder.geodata.overpass_fallback._http._retrieve_from_cache',
                   return_value=None), patch(
                'nd_route_finder.geodata.overpass_fallback.requests.post',
                return_value=SimpleNamespace(status_code=504)) as send:
            with self.assertRaises(ox._errors.ResponseStatusCodeError):
                OverpassFallback._one_shot_request(
                    OrderedDict(data='[out:json];node(47.0,15.0,47.001,15.001);out;')
                )
        self.assertEqual(send.call_count, 1)

    def test_real_data_errors_not_hidden_by_server_retry(self):
        calls = []

        def bad_input():
            calls.append(1)
            raise ValueError('invalid destination coordinate')

        with self.assertRaisesRegex(ValueError, 'invalid destination'):
            OverpassFallback().execute(bad_input, 'routing network')
        self.assertEqual(len(calls), 1)

    def test_all_unavailable_reports_short_actionable_message(self):
        with patch('nd_route_finder.geodata.overpass_fallback.time.sleep'):
            with self.assertRaises(OverpassUnavailableError) as info:
                OverpassFallback().execute(lambda: (_ for _ in ()).throw(
                    ConnectionError('connection refused')), 'road network')
        self.assertIn('Please try Generate route again later', str(info.exception))
        self.assertNotIn('connection refused', str(info.exception))

    def test_empty_result_is_not_misdiagnosed_as_network_error(self):
        with self.assertRaises(ox._errors.InsufficientResponseError):
            OverpassFallback().execute(
                lambda: (_ for _ in ()).throw(ox._errors.InsufficientResponseError('No elements')),
                'roads',
            )


if __name__ == '__main__':
    unittest.main()
