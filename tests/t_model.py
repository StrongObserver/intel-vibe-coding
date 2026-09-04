# -*- coding: utf-8 -*-
"""M1 需求模型 + 种子需求 测试。"""
from __future__ import print_function, unicode_literals
import json
import unittest
from datetime import date, timedelta

from tripengine import model, members_seed


def P(**kw):
    """便捷构造 Requirement。"""
    kw.setdefault('scope', 'group')
    return model.Requirement(**kw)


class TestModelValidation(unittest.TestCase):
    def test_unknown_dimension_rejected(self):
        with self.assertRaises(ValueError):
            P(dimension='flying_car', value={})

    def test_budget_requires_positive_int(self):
        with self.assertRaises(ValueError):
            P(dimension='budget_cap', value={'max_yuan': 0, 'unit': 'person'})
        with self.assertRaises(ValueError):
            P(dimension='budget_cap', value={'max_yuan': -5, 'unit': 'person'})
        # 数字字符串应被清洗成 int
        r = P(dimension='budget_cap', value={'max_yuan': '800', 'unit': 'person'})
        self.assertEqual(r.value['max_yuan'], 800)

    def test_budget_missing_required_field(self):
        with self.assertRaises(ValueError):
            P(dimension='budget_cap', value={'max_yuan': 800})

    def test_invalid_kind_rejected(self):
        with self.assertRaises(ValueError):
            P(dimension='pace', value={'relaxed': True}, kind='maybe')

    def test_importance_range(self):
        for bad in (0, 6, -1):
            with self.assertRaises(ValueError):
                P(dimension='history', value={'importance': 4}, importance=bad)

    def test_member_scope_requires_member(self):
        with self.assertRaises(ValueError):
            P(dimension='history', scope='member', value={'importance': 3})
        with self.assertRaises(ValueError):
            P(dimension='history', scope='member', member='ab', value={'importance': 3})

    def test_group_scope_rejects_member_too(self):
        # 群聊里常见的隐性 bug：group 约束带了 member，会被静默丢弃归属
        with self.assertRaises(ValueError):
            P(dimension='history', scope='group', member='A', value={'importance': 3})

    def test_time_and_day_format(self):
        with self.assertRaises(ValueError):
            P(dimension='return_deadline', value={'day': 'sunday', 'place': '上海',
                                                  'time': '25:00'})
        with self.assertRaises(ValueError):
            P(dimension='return_deadline', value={'day': 'funday', 'place': '上海',
                                                  'time': '18:00'})
        ok = P(dimension='return_deadline', value={'day': 'sunday', 'place': '上海',
                                                   'time': '18:00', 'buffer_min': 40})
        self.assertTrue(ok.is_hard)

    def test_default_kind_from_dimension(self):
        self.assertEqual(P(dimension='diet', value={'type': 'vegetarian'}).kind, 'hard')
        self.assertEqual(P(dimension='hot_spring', value={}).kind, 'soft')

    def test_soft_importance_attr(self):
        r = P(dimension='hot_spring', value={'want': True}, importance=4)
        self.assertEqual(r.importance, 4)
        self.assertFalse(r.is_hard)


class TestRequirementRoundtrip(unittest.TestCase):
    def test_dict_roundtrip(self):
        r = model.Requirement.from_dict(P(
            dimension='return_deadline', scope='member', member='A', kind='hard',
            value={'day': 'sunday', 'place': '上海', 'time': '18:00', 'buffer_min': 40},
            quote='q', note='n').to_dict())
        self.assertEqual(r.dimension, 'return_deadline')
        self.assertEqual(r.member, 'A')
        self.assertEqual(r.value['time'], '18:00')
        self.assertEqual(r.quote, 'q')
        self.assertEqual(r.note, 'n')

    def test_json_roundtrip_of_project(self):
        p = members_seed.build_default_project(start_date=date(2026, 9, 4))
        p2 = model.Project.from_dict(json.loads(json.dumps(p.to_dict())))
        self.assertEqual([m.id for m in p2.members], ['A', 'B', 'C', 'D', 'E', 'F'])
        self.assertEqual(len(p2.requirements), len(p.requirements))

    def test_add_remove_requirement(self):
        p = members_seed.build_default_project()
        before = len(p.requirements)
        r = P(dimension='custom', value={'text': '试一下'})
        p.add(r)
        self.assertEqual(len(p.requirements), before + 1)
        p.remove(r.rid)
        self.assertEqual(len(p.requirements), before)


class TestSeedSanity(unittest.TestCase):
    def setUp(self):
        self.p = members_seed.build_default_project(start_date=date(2026, 9, 4))

    def test_six_members_and_all_have_role(self):
        self.assertEqual(self.p.member_ids(), ['A', 'B', 'C', 'D', 'E', 'F'])

    def test_key_hard_constraints(self):
        ra = self.p.find('return_deadline', member='A', kind='hard')
        self.assertEqual(len(ra), 1)
        self.assertEqual(ra[0].value['time'], '18:00')
        dd = self.p.find('depart_earliest', member='D', kind='hard')
        self.assertEqual(len(dd), 1)
        self.assertEqual(dd[0].value['time'], '11:00')
        self.assertEqual(self.p.find('diet', member='C', kind='hard')[0].value['type'],
                         'vegetarian')
        cap = self.p.find('transport_capacity', member='F', kind='hard')[0]
        self.assertEqual(cap.value['seats'], 4)
        self.assertEqual(cap.value['driver'], 'F')

    def test_key_soft_preferences(self):
        self.assertEqual(self.p.find('budget_cap')[0].kind, 'soft')
        self.assertEqual(self.p.find('budget_cap')[0].value['max_yuan'], 800)
        self.assertEqual(self.p.find('hot_spring', member='D')[0].kind, 'soft')
        self.assertEqual(self.p.find('walk_limit', member='C')[0].importance, 5)
        self.assertEqual(self.p.find('nature_photo', member='B')[0].importance, 4)

    def test_every_requirement_has_quote_for_traceability(self):
        empty = [r.rid for r in self.p.requirements if not r.quote.strip()]
        self.assertEqual(empty, [], '所有需求都应带群聊原文出处')

    def test_member_requirements_reference_existing_members(self):
        ids = set(self.p.member_ids())
        bad = [r.member for r in self.p.requirements
               if r.scope == 'member' and r.member not in ids]
        self.assertEqual(bad, [])

    def test_hard_constraints_have_at_least_one_owner_except_transport(self):
        # 除交通载客(全员相关)外，硬约束都应能追到具体某个人
        owners = set(r.member for r in self.p.requirements if r.kind == 'hard')
        self.assertTrue('A' in owners and 'C' in owners and 'D' in owners and 'F' in owners)

    def test_default_trip_dates_are_a_weekend_pair(self):
        s = self.p.settings['trip_dates']['start']
        e = self.p.settings['trip_dates']['end']
        sd = date(*[int(x) for x in s.split('-')])
        ed = date(*[int(x) for x in e.split('-')])
        self.assertEqual(sd.weekday(), 5)          # 周六
        self.assertEqual(ed.weekday(), 6)          # 周日
        self.assertEqual((ed - sd).days, 1)

    def test_next_weekend_skips_imminent(self):
        # 周五 -> 取再下一个周末，而不是明天
        fri = date(2026, 9, 4)
        s, e = members_seed.next_weekend(fri)
        self.assertEqual(s, '2026-09-12')
        self.assertEqual(e, '2026-09-13')


if __name__ == '__main__':
    unittest.main()
