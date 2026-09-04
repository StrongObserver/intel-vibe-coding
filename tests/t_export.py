# -*- coding: utf-8 -*-
"""M5c 导出/决策总结 测试。"""
from __future__ import print_function, unicode_literals
import unittest
from datetime import date

from tripengine.members_seed import build_default_project
from tripengine.planner import generate_plans
from tripengine.export import build_export, build_open_questions, finalize_text, find_plan
from tripengine.conflicts import analyze_project


class TestExport(unittest.TestCase):
    def setUp(self):
        self.p = build_default_project(start_date=date(2026, 9, 4))
        self.res = generate_plans(self.p)
        self.plan = self.res['plans'][0]

    def test_export_contains_core_sections(self):
        text = '\n'.join(build_export(self.p, self.res, self.plan['id']))
        for must in ('目的地', '交通', '住宿', '行程', '费用', '逐人核对', '待确认'):
            self.assertIn(must, text)
        self.assertIn(self.plan['city_name'], text)
        self.assertIn('周六', text)
        self.assertIn('周日', text)

    def test_export_mentions_each_member_when_voting(self):
        votes = {'A': 'accept', 'B': 'accept', 'C': 'concerned',
                 'D': 'accept', 'E': 'accept', 'F': 'oppose'}
        text = '\n'.join(build_export(self.p, self.res, self.plan['id'], votes=votes))
        for mid in 'ABCDEF':
            self.assertIn(mid, text)
        self.assertIn('✓ 接受', text)
        self.assertIn('✗ 反对', text)
        self.assertIn('A', text)

    def test_unknown_plan_raises(self):
        with self.assertRaises(ValueError):
            find_plan(self.res, 'pl_不存在')

    def test_open_questions_bullets(self):
        analysis = analyze_project(self.p)
        bullets = build_open_questions(analysis)
        self.assertTrue(len(bullets) >= 5)
        for b in bullets:
            self.assertTrue(b.startswith('□'))
        self.assertTrue(any('F / 全员' in b for b in bullets))

    def test_finalize_text_deterministic(self):
        analysis = analyze_project(self.p)
        t1 = finalize_text(self.p, self.res, self.plan['id'], conflicts_res=analysis)
        t2 = finalize_text(self.p, self.res, self.plan['id'], conflicts_res=analysis)
        self.assertEqual(t1, t2)
        self.assertIn('拍板', t1)
        self.assertIn('□', t1)


if __name__ == '__main__':
    unittest.main()
