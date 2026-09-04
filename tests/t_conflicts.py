# -*- coding: utf-8 -*-
"""M3 冲突与不确定性分析 测试。"""
from __future__ import print_function, unicode_literals
import unittest
from datetime import date

from tripengine import model, knowledge
from tripengine.conflicts import analyze_project, rough_min_cost
from tripengine.members_seed import build_default_project


def project_with(members='ABCDEF', requirements=()):
    return model.Project(members=[model.Member(x) for x in members],
                         requirements=list(requirements),
                         settings={'trip_dates': {'start': '2026-09-12',
                                                  'end': '2026-09-13'}})


def R(dimension, scope=None, member=None, kind=None, value=None, importance=3):
    if scope is None:
        scope = 'member' if member else 'group'
    return model.Requirement(dimension, scope=scope, member=member, kind=kind,
                             value=value, importance=importance,
                             quote='测试', note='测试')


class TestSeedAnalysis(unittest.TestCase):
    def setUp(self):
        self.p = build_default_project(start_date=date(2026, 9, 4))
        self.out = analyze_project(self.p)

    def _slugs(self):
        return [c['slug'] for c in self.out['conflicts']]

    def test_core_conflicts_detected(self):
        slugs = self._slugs()
        for must in ('transport_capacity', 'dep_after_1100', 'return_deadline',
                     'vegetarian', 'photo_vs_walking', 'museum_tension', 'commercial'):
            self.assertIn(must, slugs)

    def test_budget_soft_not_hard_flag(self):
        slugs = self._slugs()
        self.assertIn('budget_hotspring', slugs)
        self.assertNotIn('budget_hotspring_hard', slugs)
        self.assertNotIn('budget_hard_global', slugs)

    def test_entry_shape(self):
        for c in self.out['conflicts']:
            self.assertIn(c['severity'], ('high', 'medium', 'info'))
            self.assertTrue(c['title'])
            self.assertTrue(c['detail'])

    def test_uncertainty_ledger_shape(self):
        slugs = {u['slug'] for u in self.out['uncertainties']}
        for must in ('trip_date', 'destination', 'weather', 'ticket_hot',
                     'museum_reserve', 'budget_define', 'origin_assume'):
            self.assertIn(must, slugs)
        for u in self.out['uncertainties']:
            self.assertTrue(u['question'] and u['owner'] and u['detail'])
            self.assertEqual(u['status'], 'open')

    def test_date_uncertainty_mentions_defaults(self):
        u = next(x for x in self.out['uncertainties'] if x['slug'] == 'trip_date')
        self.assertIn('2026-09-12', u['detail'])


class TestRules(unittest.TestCase):
    def test_no_capacity_conflict_when_seats_sufficient(self):
        p = project_with(requirements=[R('transport_capacity', member='F',
                                         value={'driver': 'F', 'seats': 6,
                                                'can_rail': True}, kind='hard')])
        slugs = [c['slug'] for c in analyze_project(p)['conflicts']]
        self.assertNotIn('transport_capacity', slugs)

    def test_capacity_conflict_when_group_bigger_than_seats(self):
        p = project_with(requirements=[R('transport_capacity', member='F',
                                         value={'driver': 'F', 'seats': 4,
                                                'can_rail': True}, kind='hard')])
        out = analyze_project(p)
        c = next(x for x in out['conflicts'] if x['slug'] == 'transport_capacity')
        self.assertEqual(c['severity'], 'medium')
        self.assertIn('2 人', c['detail'])          # 6-4=2 人须高铁

    def test_no_dep_no_ret_no_time_messages(self):
        p = project_with()
        slugs = [c['slug'] for c in analyze_project(p)['conflicts']]
        self.assertNotIn('dep_after_1100', slugs)
        self.assertNotIn('return_deadline', slugs)
        self.assertNotIn('pace_vs_time', slugs)

    def test_museum_tension_requires_both_players(self):
        p = build_default_project(start_date=date(2026, 9, 4))
        e_hist = p.find('history', member='E')[0]
        p.remove(e_hist.rid)
        slugs = [c['slug'] for c in analyze_project(p)['conflicts']]
        self.assertNotIn('museum_tension', slugs)

    def test_commercial_flag_lists_high_commercial_venues(self):
        p = build_default_project(start_date=date(2026, 9, 4))
        out = analyze_project(p)
        c = next(x for x in out['conflicts'] if x['slug'] == 'commercial')
        self.assertIn('夫子庙', c['detail'])
        self.assertIn('平江路', c['detail'])

    def test_hard_budget_under_all_cities_is_blocker(self):
        p = project_with(requirements=[
            R('budget_cap', kind='hard', importance=5,
              value={'max_yuan': 300, 'unit': 'person'}),
            R('hot_spring', member='D', kind='soft', value={'want': True}),
        ])
        slugs = [c['slug'] for c in analyze_project(p)['conflicts']]
        self.assertIn('budget_hard_global', slugs)
        self.assertIn('budget_hotspring_hard', slugs)

    def test_empty_project_has_no_conflicts_but_open_questions(self):
        p = project_with()
        out = analyze_project(p)
        self.assertEqual(out['conflicts'], [])
        self.assertTrue(out['uncertainties'])

    def test_rough_cost_ordering_and_shape(self):
        p = build_default_project(start_date=date(2026, 9, 4))
        totals = {c: rough_min_cost(p, c)['total'] for c in knowledge.city_ids()}
        self.assertLess(totals['suzhou'], totals['hangzhou'])
        self.assertLess(totals['hangzhou'], totals['nanjing'])
        # 最低开销由高铁+住宿+三餐构成，必须包含三部分
        su = rough_min_cost(p, 'suzhou')
        for part in ('rail', 'lodging', 'meals'):
            self.assertGreater(su[part], 0)


if __name__ == '__main__':
    unittest.main()
