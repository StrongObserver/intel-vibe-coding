# -*- coding: utf-8 -*-
"""端到端联动测试：模拟促导员在 UI 上完成一轮完整使用（仅走 API，等价于界面动作）。
覆盖 M1↔M3↔M4↔M5c 联动：改需求 → 冲突变化 → 方案变化 → 表决 → 定稿导出。
"""
from __future__ import print_function, unicode_literals
import unittest

from tests.t_api import req, ServerTestCase, start_server


class E2EFacilitatorJourney(ServerTestCase):
    """独立起一个服务，模拟一次完整促导。"""

    def _reset(self):
        code, body = req(self.base, '/api/reset', method='POST')
        self.assertEqual(code, 200)
        return body['project']

    def _plans(self, weather='sunny'):
        code, body = req(self.base, '/api/plans', method='POST', body={'weather': weather})
        self.assertEqual(code, 200)
        return body

    def _find_req(self, project, dimension, member=None):
        cand = [r for r in project['requirements']
                if r['dimension'] == dimension and r.get('member') == member]
        return cand[0]

    def _edit_and_save(self, mutator):
        code, st = req(self.base, '/api/state')
        p = st['project']
        mutator(p)
        code, body = req(self.base, '/api/state', method='POST', body={'project': p})
        self.assertEqual(code, 200)

    def test_budget_hard_changes_conflicts_and_plans(self):
        self._reset()
        # 1) 种子态：温泉偏好 → soft 冲突
        _, c0 = req(self.base, '/api/conflicts')
        slugs0 = {c['slug'] for c in c0['conflicts']}
        self.assertIn('budget_hotspring', slugs0)
        self.assertNotIn('budget_hard_global', slugs0)

        # 2) A 的预算改成硬性 420 → 冲突升级 + 南京/杭州被排除
        def make_hard(p):
            b = self._find_req(p, 'budget_cap')
            b['kind'] = 'hard'
            b['value']['max_yuan'] = 420
        self._edit_and_save(make_hard)
        _, c1 = req(self.base, '/api/conflicts')
        self.assertIn('budget_hard_global', {c['slug'] for c in c1['conflicts']})

        res = self._plans('sunny')
        cities = {p['city'] for p in res['plans']}
        self.assertNotIn('nanjing', cities)
        for p in res['plans']:
            self.assertLessEqual(p['cost']['total'], 420)
        note = res['city_notes'].get('nanjing', '')
        self.assertIn('预算', note)

    def test_full_decision_with_votes_export(self):
        self._reset()
        res = self._plans('sunny')
        top = res['plans'][0]
        votes = {m: 'accept' for m in 'ABCDEF'}
        code, out = req(self.base, '/api/decide', method='POST',
                        body={'plan_id': top['id'], 'votes': votes,
                              'weather': 'sunny'})
        self.assertEqual(code, 200)
        text = out['export']
        self.assertIn(top['city_name'], text)
        self.assertIn('目的地', text)
        for mid in 'ABCDEF':
            self.assertIn(mid + '：✓ 接受', text)
        self.assertIn('已明确接受', text)
        self.assertIn('□', text)          # 待确认事项带进定稿
        # 无表态也应有结果
        code2, out2 = req(self.base, '/api/decide', method='POST',
                          body={'plan_id': top['id'], 'votes': {}, 'weather': 'sunny'})
        self.assertEqual(code2, 200)
        self.assertIn('还没有人表态', out2['export'])

    def test_rain_plan_decided_and_export_marks_weather(self):
        self._reset()
        res = self._plans('rain')
        top = res['plans'][0]
        self.assertEqual(top['weather'], 'rain')
        code, out = req(self.base, '/api/decide', method='POST',
                        body={'plan_id': top['id'], 'votes': {},
                              'weather': 'rain'})
        self.assertEqual(code, 200)
        self.assertIn('【雨天版】', out['export'])

    def test_walk_hard_too_low_gives_no_solution_then_relax(self):
        self._reset()
        def hard_5000(p):
            w = self._find_req(p, 'walk_limit', member='C')
            w['kind'] = 'hard'
            w['value']['max_steps'] = 5000
        self._edit_and_save(hard_5000)
        res = self._plans('sunny')
        self.assertEqual(res['plans'], [])
        self.assertTrue(res['city_notes'])

        # 松回 soft → 恢复有解（与题目"小步快跑、保留调整空间"一致）
        def soft_back(p):
            w = self._find_req(p, 'walk_limit', member='C')
            w['kind'] = 'soft'
        self._edit_and_save(soft_back)
        res2 = self._plans('sunny')
        self.assertTrue(res2['plans'])

    def test_invalid_decide_plan_400(self):
        self._reset()
        code, out = req(self.base, '/api/decide', method='POST',
                        body={'plan_id': 'pl_不存在的', 'votes': {}})
        self.assertEqual(code, 400)


if __name__ == '__main__':
    unittest.main()
