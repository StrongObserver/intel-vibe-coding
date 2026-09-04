# -*- coding: utf-8 -*-
"""M3 冲突与不确定性分析（"冲突雷达 + 待确认清单"）。

分析是**静态、可解释**的：只做"数据/规则层面的必然推论"，
不做黑盒打分。所有条目带稳定 slug，前端可直接渲染、测试可精确断言。

severity: high = 需拍板/会让部分城市不可行
          medium = 会产生取舍/trade-off
          info   = 提示性背景
"""
from __future__ import print_function, unicode_literals

from . import knowledge

CITY_TRANSFER_MIN = 30       # 到达目的地高铁站 → 游玩区/酒店 的市内移动估算


def _first(project, dimension, member=None, kind=None):
    found = project.find(dimension, member=member, kind=kind)
    return found[0] if found else None


def rough_min_cost(project, cid):
    """每人"最低开销"粗算（不含景点门票/不含温泉），仅供预算级预警。
    口径 = 高铁往返 + 最便宜干净住宿 + 午/晚/早各一顿素食最低。
    """
    city = knowledge.CITIES[cid]
    rail_rt = 2 * city['rail_cost']
    lodging = min(l['price_pp'] for l in city['lodging'] if l.get('clean_safe'))
    lunch = min(f['cost'] for f in city['foods'] if f['kind'] == 'lunch' and f['veg'])
    dinner = min(f['cost'] for f in city['foods'] if f['kind'] == 'dinner' and f['veg'])
    meals = lunch + dinner + knowledge.BREAKFAST_COST + lunch   # D1午+D1晚+D2早+D2午
    return {'rail': rail_rt, 'lodging': lodging, 'meals': meals,
            'total': rail_rt + lodging + meals}


def _activity_pool(cid):
    return knowledge.CITIES[cid]['acts']


def analyze_project(project):
    """输入 Project，输出 {'conflicts':[], 'uncertainties':[]}。"""
    conflicts, uncertainties = [], []

    group_size = len(project.members)

    # ---------- 1) 交通载客能力 ----------
    cap = _first(project, 'transport_capacity')
    if cap and cap.value.get('seats', 99) < group_size:
        seats = cap.value['seats']
        conflicts.append({
            'slug': 'transport_capacity',
            'severity': 'medium',
            'title': '车坐不下 6 个人：交通方案必须先拍板',
            'detail': ('%s 的车只有 %d 座，而你们是 %d 人 → 若自驾，至少 %d 人必须坐高铁'
                       '；或全员高铁（F 明确说高铁也行）。这个决定会改变所有人的出发时间'
                       '与开销。') % (cap.value.get('driver', 'F'), seats, group_size,
                                     group_size - seats),
            'members': ['F'],
        })

    # ---------- 2) D 周六 11:00 后才能出发 → 首日窗口 ----------
    dep = _first(project, 'depart_earliest')
    ret = _first(project, 'return_deadline')
    dep_min = knowledge.parse_min(dep.value['time']) if dep else 8 * 60
    if dep:
        arrivals = []
        for cid in knowledge.city_ids():
            city = knowledge.CITIES[cid]
            arr = dep_min + city['rail_min'] + CITY_TRANSFER_MIN
            arrivals.append('%s≈%s 到' % (city['name'], knowledge.fmt_min(arr)))
        conflicts.append({
            'slug': 'dep_after_1100',
            'severity': 'medium',
            'title': 'D 周六 11:00 后才能出发 → 首日上午整体空掉',
            'detail': ('所有人必须等 D，Day1 上午(11:00 前)不能排任何活动。'
                       '各候选到达时间：%s。到得越晚，Day1 越像"半天"。') % '、'.join(arrivals),
            'members': ['D'],
        })

    # ---------- 3) A 周日 18:00 前回上海 → 各城市返程底线 ----------
    if ret and ret.value.get('place') in ('上海', knowledge.ORIGIN):
        deadline = ret.value.get('time', '18:00')
        lines = []
        for cid in knowledge.city_ids():
            city = knowledge.CITIES[cid]
            last = knowledge.latest_rail_departure(city['rail_min'], deadline,
                                                   ret.value.get('buffer_min', 45))
            lines.append('%s：最晚 %s 发车（单程 %d 分钟）'
                         % (city['name'], last, city['rail_min']))
        far = knowledge.CITIES['nanjing']
        conflicts.append({
            'slug': 'return_deadline',
            'severity': 'medium',
            'title': 'A 周日 %s 前必须回到上海 → 决定“第二天最晚返程时刻”'
                     % deadline,
            'detail': ('%s。对距离最远的 %s 尤其紧：最后一站基本只能排到午饭后。'
                       '这条硬线决定目的地选择上限。') % ('；'.join(lines), far['name']),
            'members': ['A'],
        })

    # ---------- 4) 素食 ----------
    diet = _first(project, 'diet', kind='hard')
    if diet and diet.value.get('type') == 'vegetarian':
        conflicts.append({
            'slug': 'vegetarian',
            'severity': 'info',
            'title': 'C 吃素 → 每顿正餐必须有素食选项',
            'detail': '内置城市(苏州/杭州/南京)的午/晚餐数据均保证至少一条素食，'
                      'C 可放心；若有人新增目的地，需要先校验该城素食覆盖。',
            'members': ['C'],
        })

    # ---------- 5) B 的自然/摄影 与 C 的腿伤 → 用"游船/少走路"替代 ----------
    walk = _first(project, 'walk_limit', member='C')
    nature = _first(project, 'nature_photo', member='B')
    if walk and nature:
        hot = []
        for cid in knowledge.city_ids():
            for a in _activity_pool(cid):
                if a.get('photography', 0) >= 8 and a.get('steps', 0) >= 10000:
                    hot.append('%s·%s(约%s步)' % (knowledge.CITIES[cid]['name'],
                                                 a['name'], a['steps']))
        conflicts.append({
            'slug': 'photo_vs_walking',
            'severity': 'medium',
            'title': 'B 想去的出片点，多数对 C 的腿不友好',
            'detail': ('B 的自然/摄影权重高，但最高质量的机位往往步行量大：%s。'
                       '破法：选步行小的替代(西湖游船/观光车)或在活动里明确 C 走'
                       '不动时"打车/放弃该点位"。C 的单日上限 %s 步。'
                       ) % ('、'.join(hot[:5]) if hot else '西湖/九溪等', walk.value['max_steps']),
            'members': ['B', 'C'],
        })

    # ---------- 6) B 反感"每天博物馆" vs 雨天/E 的历史 ----------
    mus_avoid = _first(project, 'museum_avoid', member='B')
    hist = _first(project, 'history', member='E')
    if mus_avoid and hist:
        conflicts.append({
            'slug': 'museum_tension',
            'severity': 'info',
            'title': 'E 偏爱博物馆/历史，B 不想两天都泡博物馆',
            'detail': '这不是死结：把博物馆压缩到最多 %s 天，另一天用非博物馆的历史点'
                      '(园林/陵墓/古刹)满足 E，就能同时照顾两者。遇雨时特别容易翻车。'
                      % mus_avoid.value.get('max_museum_days', 1),
            'members': ['B', 'E'],
        })

    # ---------- 7) E 反商业化 ----------
    anti = _first(project, 'avoid_commercial', member='E')
    if anti:
        limit = anti.value.get('max_level', 3)
        spots = []
        for cid in knowledge.city_ids():
            for a in _activity_pool(cid):
                if a.get('commercialization', 1) > limit:
                    spots.append('%s·%s(商业化%s/5)'
                                 % (knowledge.CITIES[cid]['name'], a['name'],
                                    a['commercialization']))
        if spots:
            conflicts.append({
                'slug': 'commercial',
                'severity': 'info',
                'title': '这些候选景点超过 E 的商业化上限(%s/5)' % limit,
                'detail': '；'.join(spots) + '。并非不能用，但排进去要给 E 解释取舍。',
                'members': ['E'],
            })

    # ---------- 8) 预算与温泉的张力 ----------
    budget = _first(project, 'budget_cap')
    hsp = _first(project, 'hot_spring', member='D')
    if budget:
        max_yuan = budget.value.get('max_yuan', 800)
        cheap_city = min(knowledge.city_ids(),
                         key=lambda c: rough_min_cost(project, c)['total'])
        rich = rough_min_cost(project, 'nanjing')
        is_hard = budget.kind == 'hard'
        if hsp and hsp.value.get('want'):
            with_hs = rich['total'] + 180     # 汤山温泉门票/泡汤
            detail = ('按人均口径：最低选项(苏州)≈%d 元；想满足 D 的温泉(南京+泡汤)'
                      '≈%d 元(高铁%s+住宿%s+三餐%s+温泉180)。'
                      % (rough_min_cost(project, cheap_city)['total'], with_hs,
                         rich['rail'], rich['lodging'], rich['meals']))
            if is_hard and with_hs > max_yuan:
                conflicts.append({
                    'slug': 'budget_hotspring_hard',
                    'severity': 'high',
                    'title': '温泉配置已超过 A 的预算硬上限(%d 元/人)' % max_yuan,
                    'detail': detail + '若这条预算真的不可破，只能牺牲温泉或改泡酒店私汤。',
                    'members': ['A', 'D'],
                })
            else:
                conflicts.append({
                    'slug': 'budget_hotspring',
                    'severity': 'medium',
                    'title': '温泉+预算 是主要拉扯点（上限 %d 元/人）' % max_yuan,
                    'detail': detail + '属 soft 约束，可以谈；但要在群里对齐口径。',
                    'members': ['A', 'D'],
                })
        if is_hard:
            over = [knowledge.CITIES[c]['name']
                    for c in knowledge.city_ids()
                    if rough_min_cost(project, c)['total'] > max_yuan]
            if over:
                conflicts.append({
                    'slug': 'budget_hard_global',
                    'severity': 'high',
                    'title': '连"最省配置"都超预算的城市：%s' % '、'.join(over),
                    'detail': '以上城市即使不买门票、不住贵房也已超 A 的硬上限，可直接排除。',
                    'members': ['A'],
                })

    # ---------- 9) 时间太紧 vs "不想太累" ----------
    pace = _first(project, 'pace')
    if dep or ret:
        conflicts.append({
            'slug': 'pace_vs_time',
            'severity': 'info',
            'title': '有效时间窗很窄，还要"不累" → 每天只配 2-3 个大项',
            'detail': ('周六 11:00 出发、周日提前返程的情况下，两天有效游玩时间'
                       '本就不多；"不想排满"意味着宁可砍项也别把时间切成碎片。'
                       '建议每天主活动 ≤3 个。'),
            'members': [],
        })

    # ================= 不确定性 / 待确认清单 =================
    def unc(slug, question, detail, owner, due=''):
        uncertainties.append({'slug': slug, 'question': question, 'detail': detail,
                              'owner': owner, 'due': due, 'status': 'open'})

    dates = project.settings.get('trip_dates', {})
    dstr = '%s~%s' % (dates.get('start', '?'), dates.get('end', '?'))
    unc('trip_date', '具体周末到底是哪天？',
        '默认按%s 估算，但群聊只说"下周末"。请先确认日期，再谈订票/订房。'
        % dstr, '全员', '订房前')
    unc('destination', '目的地最终选哪？(苏州/杭州/南京/其他)',
        '候选城市未定。方案只有在选完城市+交通方式后才能订房订票。', '全员', '越早越好')
    unc('weather', '那两天天气如何？',
        '直接影响"户外为主"还是"雨天室内预案"。建议出发前 1-2 天查并敲定备用。',
        '全员', '出发前 1-2 天')
    unc('ticket_hot', '高铁票要不要早点买？',
        'F 提醒"热门时间早点订"。周日傍晚返程/周六上午出发班次偏热，越早订越从容。',
        'F / 全员', '确认日期+城市后立即')
    unc('museum_reserve', '涉及博物馆是否都已预约？',
        '苏博/南博/浙博 等热门馆节假日需预约；若雨天临时转室内，预约可能已满。',
        '全员', '出发前 1 天查')
    unc('budget_define', '“预算 800 以内”的口径？',
        '当前按"整趟人均≤800"(高铁+住宿+餐饮+门票 AA)。是否含门票？是否 A 个人口径？'
        '请对齐后再用它做硬判断。', 'A', '选方案前')
    unc('origin_assume', '全员是否都从上海出发？',
        '返程"回到上海"与所有高铁时间都按上海算。若不是，需改出发地重新测算。',
        '全员', '选方案前')
    unc('D_schedule', 'D 周六上午的事能否挪早/晚些？',
        '11:00 出发是硬约束；若实际能 10:00 走，Day1 会宽裕一截。', 'D', '可选')
    unc('driving_plan', '是否真的让 F 开车？',
        '若开车：4 座坐 F+3 人，另 2 人高铁，需确定集合点/谁坐车/谁坐高铁；'
        '全员高铁则无此复杂度。', 'F', '订票前')

    return {'conflicts': conflicts, 'uncertainties': uncertainties}
