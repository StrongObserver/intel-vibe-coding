# -*- coding: utf-8 -*-
"""M2 目的地知识库测试。"""
from __future__ import print_function, unicode_literals
import unittest

from tripengine import knowledge


class TestKbComplete(unittest.TestCase):
    def test_validate_kb_passes(self):
        self.assertEqual(knowledge.validate_kb(), [])

    def test_covers_mentioned_cities(self):
        names = {knowledge.CITIES[c]['name'] for c in knowledge.city_ids()}
        for must in ('苏州', '杭州', '南京'):
            self.assertIn(must, names)

    def test_each_city_has_dish_vegetarian_lunch_and_dinner(self):
        for cid in knowledge.city_ids():
            kinds = {'lunch': [], 'dinner': []}
            for f in knowledge.CITIES[cid]['foods']:
                kinds[f['kind']].append(f)
            for kind, foods in kinds.items():
                self.assertTrue(any(f['veg'] for f in foods),
                                '%s 缺素食 %s' % (cid, kind))

    def test_each_city_has_two_clean_safe_lodging(self):
        for cid in knowledge.city_ids():
            safe = [l for l in knowledge.CITIES[cid]['lodging'] if l['clean_safe']]
            self.assertGreaterEqual(len(safe), 2, cid)

    def test_each_city_has_rain_alternatives(self):
        for cid in knowledge.city_ids():
            self.assertGreaterEqual(len(knowledge.CITIES[cid]['rain_acts']), 2, cid)

    def test_nanjing_has_hotspring_somewhere(self):
        kinds = [a['type'] for a in knowledge.CITIES['nanjing']['acts']
                 + knowledge.CITIES['nanjing']['rain_acts']]
        self.assertIn('hotspring', kinds)
        # 反证：苏州/杭州没有"正经温泉"，D 的偏好会自然把讨论引向南京的取舍
        for cid in ('suzhou', 'hangzhou'):
            all_types = [a['type'] for a in knowledge.CITIES[cid]['acts']
                         + knowledge.CITIES[cid]['rain_acts']]
            self.assertNotIn('hotspring', all_types)

    def test_photography_and_history_material_everywhere(self):
        for cid in knowledge.city_ids():
            acts = knowledge.CITIES[cid]['acts']
            self.assertTrue(any(a.get('photography', 0) >= 7 or a['type'] == 'nature'
                                for a in acts), '%s 无摄影友好活动' % cid)
            self.assertTrue(any(a.get('history', 0) >= 7 for a in acts),
                            '%s 无历史素材' % cid)

    def test_each_city_has_indoor_activity_in_normal_pool(self):
        # 半晴半雨的天也能换室内
        for cid in knowledge.city_ids():
            self.assertTrue(any(a['indoor'] for a in knowledge.CITIES[cid]['acts']),
                            '%s 正常活动池无室内项' % cid)

    def test_activity_ids_unique(self):
        seen = set()
        for cid in knowledge.city_ids():
            for a in knowledge.CITIES[cid]['acts'] + knowledge.CITIES[cid]['rain_acts']:
                key = (cid, a['id'])
                self.assertNotIn(key, seen)
                seen.add(key)

    def test_lodging_prices_consistent_with_economy_brief(self):
        for cid in knowledge.city_ids():
            for l in knowledge.CITIES[cid]['lodging']:
                self.assertLessEqual(l['price_pp'], 300,
                                     '%s %s 超出"不豪华"预算口径' % (cid, l['name']))


class TestTimeHelpers(unittest.TestCase):
    def test_fmt_parse_roundtrip(self):
        self.assertEqual(knowledge.parse_min('18:00'), 1080)
        self.assertEqual(knowledge.fmt_min(1080), '18:00')
        self.assertEqual(knowledge.fmt_min(945), '15:45')

    def test_latest_departure_math(self):
        # 苏州 rail 35min：16:40 发车可在 18:00 前到
        self.assertEqual(knowledge.latest_rail_departure(35), '16:40')
        # 南京 rail 90min：15:45 是底线
        self.assertEqual(knowledge.latest_rail_departure(90), '15:45')
        # 不可能：即使 0:00 出发也来不及 → None
        self.assertIsNone(knowledge.latest_rail_departure(1100))
        # 极慢车次也能"早走早到"，返回的是最晚仍可行发车时刻
        self.assertEqual(knowledge.latest_rail_departure(600), '07:15')

    def test_all_cities_returnable_by_deadline(self):
        # A 的 18:00 截止：每座城市最晚发车都不早于 15:30，意味着"上午主景点+午餐"结构可行
        for cid in knowledge.city_ids():
            dep = knowledge.latest_rail_departure(knowledge.CITIES[cid]['rail_min'])
            self.assertIsNotNone(dep, cid)
            self.assertGreaterEqual(knowledge.parse_min(dep), knowledge.parse_min('15:30'),
                                    '%s 返程窗口过紧' % cid)


if __name__ == '__main__':
    unittest.main()
