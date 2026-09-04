# -*- coding: utf-8 -*-
"""M4 方案生成与打分 测试。"""
from __future__ import print_function, unicode_literals
import json
import unittest
from datetime import date

from tripengine import knowledge
from tripengine.members_seed import build_default_project
from tripengine.planner import generate_plans, validate_plan


def default_p():
    return build_default_project(start_date=date(2026, 9, 4))


def _last_dep(cid):
    return knowledge.parse_min('18:00') - knowledge.CITIES[cid]['rail_min'] - 45


class TestPlansBasic(unittest.TestCase):
    def setUp(self):
        self.res = generate_plans(default_p(), weather='sunny')

    def test_returns_plans_and_covers_all_cities(self):
        self.assertTrue(self.res['plans'])
        cities = {p['city'] for p in self.res['plans']}
        self.assertTrue({'suzhou', 'hangzhou', 'nanjing'} <= cities)

    def test_every_plan_passes_hard_validator(self):
        for p in self.res['plans']:
            ok, reasons = validate_plan(default_p(), p)
            self.assertTrue(ok, '%s: %s' % (p['id'], reasons))

    def test_return_deadline_respected_for_each_city(self):
        for p in self.res['plans']:
            dep = p['days'][1]['return_dep']
            self.assertLessEqual(dep, _last_dep(p['city']), p['id'])

    def test_day1_starts_at_or_after_1100(self):
        for p in self.res['plans']:
            first = p['days'][0]['blocks'][0]
            self.assertIn('出发', first['when'])
            t = first['when'].split('出发')[0].replace('约 ', '').strip()
            self.assertGreaterEqual(knowledge.parse_min(t), 11 * 60, p['id'])

    def test_budget_soft_still_gives_under800_option(self):
        self.assertTrue(any(p['cost']['total'] <= 800 for p in self.res['plans']))

    def test_plan_shape(self):
        for p in self.res['plans']:
            self.assertEqual(len(p['days']), 2)
            for d in p['days']:
                self.assertGreater(d['steps_est'], 0)
                self.assertTrue(d['blocks'])
                for b in d['blocks']:
                    self.assertTrue(b.get('when') and b.get('title'))
            for part in ('transport', 'lodging', 'food', 'activities', 'total'):
                self.assertGreaterEqual(p['cost'][part], 0)
                self.assertIsInstance(p['cost'][part], int)

    def test_gaps_shape_and_membership(self):
        for p in self.res['plans']:
            known = set('ABCDEF') | {'GROUP'}
            for mid, gaps in p['gaps'].items():
                self.assertIn(mid, known)
                for g in gaps:
                    self.assertIn('dimension', g)
                    self.assertTrue(g.get('why'))

    def test_transport_seats_consistent(self):
        for p in self.res['plans']:
            tr = p['transport']
            if tr['mode'] == 'car+rail':
                self.assertEqual(len(tr['rail_riders']) + tr['car_seats'], 6)
            else:
                self.assertEqual(len(tr['rail_riders']), 6)

    def test_deterministic(self):
        r2 = generate_plans(default_p(), weather='sunny')
        self.assertEqual([(p['id'], p['match'], p['acts_slug']) for p in self.res['plans']],
                         [(p['id'], p['match'], p['acts_slug']) for p in r2['plans']])
        self.assertEqual(json.dumps(self.res, ensure_ascii=False, sort_keys=True),
                         json.dumps(r2, ensure_ascii=False, sort_keys=True))


class TestHardFilters(unittest.TestCase):
    def test_walk_hard_eliminates_heavy_plans(self):
        p = default_p()
        p.find('walk_limit', member='C')[0].kind = 'hard'
        p.find('walk_limit', member='C')[0].value['max_steps'] = 14000
        res = generate_plans(p)
        self.assertTrue(res['plans'])
        for pl in res['plans']:
            self.assertLessEqual(max(d['steps_est'] for d in pl['days']), 14000)
            ok, _ = validate_plan(p, pl)
            self.assertTrue(ok)

    def test_walk_hard_impossible_reports_no_solution(self):
        p = default_p()
        p.find('walk_limit', member='C')[0].kind = 'hard'
        p.find('walk_limit', member='C')[0].value['max_steps'] = 5000
        res = generate_plans(p)
        self.assertEqual(res['plans'], [])
        self.assertTrue(res['city_notes'], '无解时应给出城市级说明')

    def test_budget_hard_caps_total(self):
        p = default_p()
        b = p.find('budget_cap')[0]
        b.kind = 'hard'
        b.value['max_yuan'] = 500
        res = generate_plans(p)
        for pl in res['plans']:
            self.assertLessEqual(pl['cost']['total'], 500)
            ok, _ = validate_plan(p, pl)
            self.assertTrue(ok)

    def test_budget_hard_excludes_unaffordable_city(self):
        p = default_p()
        b = p.find('budget_cap')[0]
        b.kind = 'hard'
        b.value['max_yuan'] = 400          # 南京最低 585 > 400
        res = generate_plans(p)
        self.assertNotIn('nanjing', {pl['city'] for pl in res['plans']})
        self.assertIn('nanjing', res['city_notes'])


class TestRain(unittest.TestCase):
    def setUp(self):
        self.res = generate_plans(default_p(), weather='rain')

    def test_rain_plans_all_indoor(self):
        self.assertTrue(self.res['plans'])
        for p in self.res['plans']:
            self.assertEqual(p['weather'], 'rain')
            for d in p['days']:
                for b in d['blocks']:
                    if b.get('act'):
                        self.assertTrue(b['act']['indoor'],
                                        '%s 雨天仍含户外项 %s' % (p['id'], b['title']))

    def test_rain_not_two_museum_days(self):
        for p in self.res['plans']:
            museum_days = {d['di'] for d in p['days']
                           for b in d['blocks']
                           if b.get('act') and b['act']['type'] == 'museum'}
            self.assertLessEqual(len(museum_days), 1, p['id'])


class TestDandOther(unittest.TestCase):
    def test_hotspring_preference_creates_gap_in_non_nanjing(self):
        res = generate_plans(default_p())
        gaps_d = {p['city']: p['gaps'].get('D', []) for p in res['plans']}
        non_nj = [c for c in gaps_d if c != 'nanjing']
        self.assertTrue(non_nj)
        for c in non_nj:
            self.assertTrue(any(g['dimension'] == 'hot_spring' for g in gaps_d[c]),
                            '%s 应因无温泉给 D 亮缺口' % c)

    def test_history_unmet_never_happens_in_nanjing_plans(self):
        res = generate_plans(default_p())
        for p in res['plans']:
            if p['city'] == 'nanjing':
                gaps_e = p['gaps'].get('E', [])
                self.assertFalse(any(g['dimension'] == 'history' for g in gaps_e))


if __name__ == '__main__':
    unittest.main()
