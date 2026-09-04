# -*- coding: utf-8 -*-
"""默认种子需求：从题目给定的"群聊原文"逐条提取 A–F 六人与全员级需求。

提取口径（也是产品核心判断，全部带 quote 可追溯、note 说明依据、可在 UI 改）：
* hard = 硬约束（"必须 / 最快…才能 / 只能 / 我吃素"）→ 方案必须满足；
* soft = 偏好（"最好 / 不想 / 比较想 / 希望"）→ 打分与权衡，可被牺牲但要明示。
"""
from __future__ import print_function
from datetime import date, timedelta

from .model import Project, Member, Requirement


def next_weekend(start=None):
    """取"下周末"(周六+周日)。若本周末近在 3 天内则顺延一周——
    群聊里的"下周末"通常是提前规划而非明后天。日期仍须在 UI 确认。"""
    d = start or date.today()
    sat = d + timedelta(days=(5 - d.weekday()) % 7)
    if (sat - d).days < 3:
        sat = sat + timedelta(days=7)
    return sat.isoformat(), (sat + timedelta(days=1)).isoformat()


def build_default_project(start_date=None):
    """按群聊内容构造初始 Project。所有数值都可后续在 UI 修改。"""
    members = [Member(x) for x in 'ABCDEF']

    reqs = [
        # ---------------- A ----------------
        Requirement(
            'return_deadline', scope='member', member='A', kind='hard',
            value={'day': 'sunday', 'place': '上海', 'time': '18:00', 'buffer_min': 40},
            quote='A：我周日晚上 6 点之前必须回到上海。',
            note='硬截止：Day2 全部安排与返程必须在 18:00 前到上海（含 40 分钟离站缓冲）。'
                 '这是全项目最硬的"时间锚"，会反向约束目的地的可去性。'),
        Requirement(
            'budget_cap', scope='group', kind='soft', importance=5,
            value={'max_yuan': 800, 'unit': 'person'},
            quote='A：预算最好控制在 800 元以内',
            note='按"整趟人均 ≤800"(高铁+住宿+餐饮+门票 AA 后)理解——这是最常见口径，'
                 '已作为假设标注，可在 UI 改为"整趟"或修改金额。'),
        # ---------------- B ----------------
        Requirement(
            'nature_photo', scope='member', member='B', kind='soft', importance=4,
            value={'importance': 4},
            quote='B：我主要想拍照，最好有自然风景',
            note='需要至少若干"自然/出片"型活动；打分按活动 nature/photography 标签给分。'),
        Requirement(
            'museum_avoid', scope='member', member='B', kind='soft', importance=4,
            value={'max_museum_days': 1},
            quote='B：我不想两天都在逛博物馆',
            note='不是"不能有博物馆"，而是不能"每天都是博物馆"→ 上限 1 个全天。'),
        # ---------------- C ----------------
        Requirement(
            'diet', scope='member', member='C', kind='hard',
            value={'type': 'vegetarian'},
            quote='C：我吃素',
            note='硬性：每天每顿正餐必须标注素食选项可用；活动数据里按"有无素食"校验。'),
        Requirement(
            'walk_limit', scope='member', member='C', kind='soft', importance=5,
            value={'max_steps': 12000},
            quote='C：最近腿不太舒服，最好不要一天走特别多路',
            note='软上限：默认 12000 步/天（权重最高），超过会给该成员亮黄灯；'
                 '可切成 hard 来制造"无解"教学场景。'),
        # ---------------- D ----------------
        Requirement(
            'depart_earliest', scope='member', member='D', kind='hard',
            value={'day': 'saturday', 'time': '11:00'},
            quote='D：我周六上午有事情，最快 11 点以后才能出发',
            note='硬性：Day1 上午(11:00 前)不能排任何活动/必须等人齐后出发。'
                 '这会显著压缩"远距离目的地"的第一天。'),
        Requirement(
            'hot_spring', scope='member', member='D', kind='soft', importance=4,
            value={'want': True},
            quote='D：我比较想泡温泉',
            note='偏好：希望至少出现一次温泉类活动；若无则给 D 亮"未满足"。'),
        # ---------------- E ----------------
        Requirement(
            'history', scope='member', member='E', kind='soft', importance=4,
            value={'importance': 4},
            quote='E：我喜欢有历史感的地方',
            note='偏好：希望覆盖历史/古建/文博类活动。'),
        Requirement(
            'avoid_commercial', scope='member', member='E', kind='soft', importance=3,
            value={'max_level': 3},
            quote='E：不太喜欢特别商业化的景点',
            note='偏好：活动数据含 commercialization 1-5，超过 max_level 会扣 E 的分并提示。'),
        # ---------------- F ----------------
        Requirement(
            'transport_capacity', scope='member', member='F', kind='hard',
            value={'driver': 'F', 'seats': 4, 'can_rail': True},
            quote='F：我可以开车，不过我的车只能坐 4 个人。坐高铁也可以，但热门时间最好早点订',
            note='硬事实：6 人 > 4 座 → 若 F 开车，其余 ≥2 人须坐高铁；'
                 '也可全员高铁。"热门票早订"进入待办清单。'),
        # ---------------- 全员级 ----------------
        Requirement(
            'pace', scope='group', kind='soft', importance=4,
            value={'relaxed': True},
            quote='A：最好不要太累。 / 大家都不想把行程排得特别满。',
            note='偏好：每天日块数、总移动时间设上限；宁可少而精。'),
        Requirement(
            'lodging', scope='group', kind='soft', importance=4,
            value={'clean_safe': True, 'economy': True},
            quote='住宿希望干净、安全，不需要特别豪华',
            note='偏好：选干净安全的经济型住宿，豪华/网红不作为加分项。'),
        Requirement(
            'weather_backup', scope='group', kind='soft', importance=4,
            value={'indoor_plan': True},
            quote='如果天气不好，希望最好还有一些室内活动可以替代',
            note='偏好：方案里每个日块要能"一键切雨天版"；D 天气不决 → 待确认。'),
        Requirement(
            'origin', scope='group', kind='soft',
            value={'city': '上海'},
            quote='（群聊未明说）',
            note='假设：全员从上海出发，返程以"到上海"计。可改。'),
        Requirement(
            'trip_window', scope='group', kind='hard',
            value={'nights': 1, 'start_day': 'saturday', 'end_day': 'sunday'},
            quote='（题目给定）',
            note='两天一夜、周六出发周日返回。'),
    ]

    sat, sun = next_weekend(start_date)
    settings = {
        'trip_dates': {'start': sat, 'end': sun},
        'date_note': '默认取"下周末"的估算值，请务必在群内确认实际日期',
        'origin_city': '上海',
        'group_label': '6 人两天一夜周末旅行',
    }
    return Project(members=members, requirements=reqs, settings=settings)
