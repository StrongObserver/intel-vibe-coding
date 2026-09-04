# -*- coding: utf-8 -*-
"""M5 HTTP 服务 + API 集成测试：真实起服、真实 HTTP 往返。"""
from __future__ import print_function, unicode_literals
import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.request
import urllib.error
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server():
    port = free_port()
    env = dict(os.environ, PORT=str(port))
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'app.py')],
                            cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = 'http://127.0.0.1:%d' % port
    for _ in range(60):
        if proc.poll() is not None:
            raise RuntimeError('server 启动失败')
        try:
            urllib.request.urlopen(base + '/api/state', timeout=1).read()
            return proc, base
        except Exception:
            time.sleep(0.15)
    proc.kill()
    raise RuntimeError('server 超时未就绪')


def req(base, path, method='GET', body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def raw(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, resp.read().decode('utf-8')


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc, cls.base = start_server()

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)


class TestApiSemantics(ServerTestCase):
    def test_state_roundtrip(self):
        code, body = req(self.base, '/api/state')
        self.assertEqual(code, 200)
        p = body['project']
        self.assertEqual([m['id'] for m in p['members']], list('ABCDEF'))
        self.assertTrue(p['requirements'])

    def test_meta_has_dimension_and_city_summaries(self):
        code, body = req(self.base, '/api/meta')
        self.assertEqual(code, 200)
        self.assertIn('budget_cap', body['dimensions'])
        self.assertEqual(body['cities']['nanjing']['name'], '南京')

    def test_reset_needs_post(self):
        code, _ = req(self.base, '/api/reset', method='GET')
        self.assertEqual(code, 405)
        code, body = req(self.base, '/api/reset', method='POST')
        self.assertEqual(code, 200)
        self.assertEqual(len(body['project']['members']), 6)

    def test_post_invalid_project_is_400(self):
        code, body = req(self.base, '/api/state', method='POST', body={
            'project': {'members': [], 'requirements': [{'dimension': '不存在的维度',
                                                         'value': {}}]}})
        self.assertEqual(code, 400)
        self.assertIn('error', body)

    def test_unknown_api_404(self):
        code, _ = req(self.base, '/api/nope')
        self.assertEqual(code, 404)

    def test_bad_weather_400(self):
        code, body = req(self.base, '/api/plans', method='POST', body={'weather': 'snow'})
        self.assertEqual(code, 400)
        self.assertIn('weather', body['error'])

    def test_bad_json_body_400(self):
        r = urllib.request.Request(self.base + '/api/plans', data=b'{bad',
                                   method='POST')
        try:
            urllib.request.urlopen(r)
            self.fail('应报 400')
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_conflicts_and_uncertainties_shape(self):
        code, body = req(self.base, '/api/conflicts')
        self.assertEqual(code, 200)
        self.assertTrue(body['conflicts'])
        self.assertTrue(body['uncertainties'])
        self.assertTrue(all('slug' in c for c in body['conflicts']))


class TestStaticAndGenerate(ServerTestCase):
    def test_index_served(self):
        code, body = raw(self.base, '/index.html')
        self.assertEqual(code, 200)
        self.assertIn('旅行决策工作台', body)

    def test_assets_exist(self):
        for f in ('/style.css', '/app.js'):
            code, _ = raw(self.base, f)
            self.assertEqual(code, 200, f)

    def test_root_serves_index(self):
        code, body = raw(self.base, '/')
        self.assertEqual(code, 200)
        self.assertIn('旅行决策工作台', body)

    def test_missing_static_404(self):
        code, _ = req(self.base, '/no-such-file.txt')
        self.assertEqual(code, 404)

    def test_generate_sunny_plans(self):
        code, body = req(self.base, '/api/plans', method='POST', body={'weather': 'sunny'})
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(body['plans']), 3)
        cities = {p['city'] for p in body['plans']}
        self.assertTrue({'suzhou', 'hangzhou', 'nanjing'} <= cities)

    def test_generate_rain_plans_indoor(self):
        code, body = req(self.base, '/api/plans', method='POST', body={'weather': 'rain'})
        self.assertEqual(code, 200)
        for p in body['plans']:
            for d in p['days']:
                for b in d['blocks']:
                    if b.get('act'):
                        self.assertTrue(b['act']['indoor'])

    def test_export_via_get(self):
        _, plans = req(self.base, '/api/plans', method='POST', body={'weather': 'sunny'})
        pid = plans['plans'][0]['id']
        code, body = req(self.base, '/api/export?plan_id=' + quote(pid))
        self.assertEqual(code, 200)
        self.assertIn('目的地', body['export'])


if __name__ == '__main__':
    unittest.main()
