#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""六人旅行决策工作台 —— 本地 Web 服务器(纯 Python3 标准库)。

运行：python app.py           → 打开 http://127.0.0.1:8000
依赖：无（Python >= 3.6）。
数据：默认从群聊种子载入；如需持久化你的修改，传 --save 会在退出前写入 state.json。
"""
from __future__ import print_function, unicode_literals

import json
import os
import re
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tripengine import members_seed, model
from tripengine.conflicts import analyze_project
from tripengine.planner import generate_plans
from tripengine.export import finalize_text

ROOT = os.path.dirname(os.path.abspath(__file__))
WWW = os.path.join(ROOT, 'www')
STATE_FILE = os.path.join(ROOT, 'state.json')

CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.ico': 'image/x-icon',
}

# 服务器持有的"当前项目状态"。默认每次启动都是群聊种子，可 /api/reset 恢复。
_project = members_seed.build_default_project()


def _save_state():
    if SAVE_ON_EXIT:
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(_project.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError:
            pass


SAVE_ON_EXIT = '--save' in sys.argv


def _load_state_if_exists():
    global _project
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding='utf-8') as f:
                _project = model.Project.from_dict(json.load(f))
        except (ValueError, OSError, KeyError):
            pass


class Handler(BaseHTTPRequestHandler):
    # 安静一些
    def log_message(self, *a):
        pass

    # ---------- 路由 ----------
    def _send(self, code, payload, ctype):
        data = payload if isinstance(payload, bytes) else payload.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), CONTENT_TYPES['.json'])

    def _err(self, code, msg):
        self._json(code, {'error': msg})

    def _read_body(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length > 2 * 1024 * 1024:
                raise ValueError('请求体过大')
            raw = self.rfile.read(length) if length else b'{}'
            return json.loads(raw.decode('utf-8'))
        except ValueError as e:
            raise ValueError('请求体不是合法 JSON：%s' % e)

    # ---------- API ----------
    def _api_state(self):
        return {'project': _project.to_dict(),
                'settings': _project.settings}

    def _api(self, path):
        if path == '/api/state':
            return self._json(200, self._api_state())
        if path == '/api/conflicts':
            return self._json(200, analyze_project(_project))
        if path == '/api/help':
            return self._json(200, {'endpoints': [
                'GET  /api/state', 'POST /api/state', 'POST /api/reset',
                'GET  /api/conflicts', 'POST /api/plans', 'POST /api/decide']})
        if path == '/api/meta':
            return self._json(200, _meta())
        if path == '/api/reset':
            return self._json(405, {'error': 'reset 用 POST'})
        return None

    def do_GET(self):
        path = self.path.split('?')[0]
        api = self._api(path)
        if api is not None:
            return
        if path == '/api/export':
            q = _parse_qs(self.path)
            plan_id = q.get('plan_id', [''])[0]
            if not plan_id:
                return self._err(400, '缺少 plan_id')
            try:
                res = generate_plans(_project)
                text = finalize_text(_project, res, plan_id,
                                     conflicts_res=analyze_project(_project))
            except (ValueError, KeyError) as e:
                return self._err(400, str(e))
            return self._json(200, {'export': text})
        self._static(path)

    def _static(self, path):
        if path in ('/', ''):
            path = '/index.html'
        rel = re.sub(r'^/', '', path)
        fp = os.path.normpath(os.path.join(WWW, rel))
        if not fp.startswith(os.path.abspath(WWW)):
            return self._err(403, '禁止路径')
        if not os.path.isfile(fp):
            return self._err(404, 'not found: %s' % path)
        ext = os.path.splitext(fp)[1].lower()
        ctype = CONTENT_TYPES.get(ext, 'application/octet-stream')
        with open(fp, 'rb') as f:
            return self._send(200, f.read(), ctype)

    def do_POST(self):
        path = self.path.split('?')[0]
        global _project
        if path == '/api/state':
            try:
                body = self._read_body()
                new_p = model.Project.from_dict(body.get('project', body))
                # 触发一次自检，避免非法项目进入后续环节
                analyze_project(new_p)
            except (ValueError, KeyError) as e:
                return self._err(400, '项目数据不合法：%s' % e)
            _project = new_p
            return self._json(200, self._api_state())
        if path == '/api/reset':
            _project = members_seed.build_default_project()
            return self._json(200, self._api_state())
        if path == '/api/plans':
            try:
                body = self._read_body()
                weather = body.get('weather', 'sunny')
                if weather not in ('sunny', 'rain'):
                    return self._err(400, 'weather 须为 sunny/rain')
                res = generate_plans(_project, weather=weather)
            except (ValueError, KeyError) as e:
                return self._err(400, str(e))
            return self._json(200, res)
        if path == '/api/decide':
            try:
                body = self._read_body()
                plan_id = body.get('plan_id', '')
                votes = body.get('votes', {})
                weather = body.get('weather', 'sunny')
                if weather not in ('sunny', 'rain'):
                    return self._err(400, 'weather 须为 sunny/rain')
                res = generate_plans(_project, weather=weather)
                analysis = analyze_project(_project)
                text = finalize_text(_project, res, plan_id, votes=votes,
                                     conflicts_res=analysis)
            except (ValueError, KeyError) as e:
                return self._err(400, str(e))
            return self._json(200, {'export': text, 'plan_id': plan_id})
        self._err(404, 'unknown api: %s' % path)


def _meta():
    from tripengine import knowledge
    dims = {k: {'label': v['label'], 'default_kind': model.DEFAULT_KIND_BY_DIMENSION.get(k),
                'value_keys': list(v['value'].keys())}
            for k, v in model.DIMENSION_SCHEMAS.items()}
    cities = {cid: {'name': c['name'], 'pros': c['pros'], 'cons': c['cons'],
                    'veg_note': c['veg_note'],
                    'acts': len(c['acts']), 'rain_acts': len(c['rain_acts']),
                    'lodging': [l['name'] for l in c['lodging']]}
               for cid, c in knowledge.CITIES.items()}
    return {'dimensions': dims, 'cities': cities, 'city_order': knowledge.CITY_ORDER}


def _parse_qs(raw_path):
    out = {}
    if '?' in raw_path:
        for kv in raw_path.split('?', 1)[1].split('&'):
            if '=' in kv:
                k, v = kv.split('=', 1)
                out.setdefault(k, []).append(v)
    return out


class ThreadedServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    port = int(os.environ.get('PORT', '8000'))
    _load_state_if_exists()
    server = ThreadedServer(('127.0.0.1', port), Handler)
    print('=' * 58)
    print('  六人周末旅行决策工作台 已启动')
    print('  请在浏览器打开:  http://127.0.0.1:%d' % port)
    print('  停止: Ctrl+C')
    print('=' * 58)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _save_state()
        server.server_close()


if __name__ == '__main__':
    main()
