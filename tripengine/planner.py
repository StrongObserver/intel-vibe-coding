# -*- coding: utf-8 -*-
"""M4 方案生成与打分引擎。

思路（确定性启发式，不依赖外部求解器）：
1) 先定"两日骨架"——硬约束已框死可用时间：周六 11:00 后出发、周日 A 须 18:00
   前回上海、全员"不想太累"，所以每天只排 1 个上下午主项 + 至多 1 个晚间轻量项。
2) 城市 × 交通(全员高铁 / F 开车+2人高铁) × 合法日块 → 硬约束过滤 → 软偏好打分。
3) 雨天：把非室内活动替换成该城室内池，并尽量别让两天都变博物馆。
输出可序列化给前端；validate_plan 为独立硬约束校验器，测试与 API 复用。

诚实性：时间为"约"、价格为每人估算，均可编辑；方案自带逐人说明(gaps)。
"""
from __future__ import print_function, unicode_literals

from . import knowledge
from .conflicts import rough_min_cost

BASE_DAILY_STEPS = 3000     # 城市内转场/逛吃基础步量(估算)
TRANSFER_CITY = 30          # 高铁站 → 游玩区
TRANSFER_STATION = 45       # 游玩区 → 高铁站 + 取行李缓冲
LUNCH_MIN, DINNER_MIN = 60, 60
DEFAULT_AM_START = 9 * 60   # 周日 9:00 开始上午主项


# ---------------------------------------------------------------- 交通
def _car_share_pp(drive_min):
    return max(20, int(drive_min * 1.2 / 4.0 / 5) * 5)


def transport_options(project, cid):
    city = knowledge.CITIES[cid]
    _caps = project.find('transport_capacity', kind='hard')
    cap = _caps[0] if _caps else None
    base = {
        'mode': 'all_rail', 'name': '全员高铁', 'rail_riders': [m.id for m in project.members],
        'car_seats': len(project.members),
        'note': city['rail_note'],
    }
    opts = [base]
    if cap and cap.value.get('can_rail') is not False:
        seats = cap.value.get('seats', 4)
        if seats < len(project.members):
            driver = cap.value.get('driver', 'F')
            others = [m.id for m in project.members if m.id != driver]
            riders = [x for x in ('A', 'C') if x in others]
            need = len(project.members) - seats
            riders += [x for x in others if x not in riders][:need - len(riders)]
            opts.append({
                'mode': 'car+rail', 'name': '%s开车 + %d 人高铁' % (driver, need),
                'rail_riders': riders, 'car_seats': seats,
                'note': ('车只能坐 %d 人：%s、%s 走高铁(时间更可控)；自驾组需在目的地会合，'
                         '集合时刻与谁坐哪辆车须在群里敲定。') % (
                    seats, '、'.join(riders), '或按实际调整'),
            })
    return opts


def _person_transport_cost(project, cid, mode, member_id):
    city = knowledge.CITIES[cid]
    rail_rt = 2 * city['rail_cost']
    if mode == 'all_rail':
        return rail_rt
    opt = next(o for o in transport_options(project, cid) if o['mode'] == mode)
    if member_id in opt['rail_riders']:
        return rail_rt
    return _car_share_pp(city['drive_min'])


# ---------------------------------------------------------------- 餐饮
def pick_meals(cid):
    """每顿都选有素食档口（C 吃素优先），再取素食中最低价。"""
    by_kind = {}
    for f in knowledge.CITIES[cid]['foods']:
        by_kind.setdefault(f['kind'], []).append(f)
    lunch = min((f for f in by_kind['lunch'] if f['veg']), key=lambda f: f['cost'])
    dinner = min((f for f in by_kind['dinner'] if f['veg']), key=lambda f: f['cost'])
    total = lunch['cost'] * 2 + dinner['cost'] + knowledge.BREAKFAST_COST
    return [lunch, lunch, dinner], total


# ---------------------------------------------------------------- 打分
def _find_act(city, act_id):
    for pool in (city['acts'], city['rain_acts']):
        for a in pool:
            if a['id'] == act_id:
                return a
    raise KeyError(act_id)


def _soft_ok(dimension, req, ctx):
    """判断一条 soft 需求是否被 ctx 代表的方案满足。返回 (ok, 说明)。"""
    if dimension == 'budget_cap':
        cap = req.value.get('max_yuan', 800)
        return ctx['total_pp'] <= cap, '人均约%d 元(上限 %d)' % (ctx['total_pp'], cap)
    if dimension == 'nature_photo':
        return ctx['has_nature_photo'], '有自然/出片类主项' if ctx['has_nature_photo'] else '无自然类主项'
    if dimension == 'museum_avoid':
        cap = req.value.get('max_museum_days', 1)
        return ctx['museum_days'] <= cap, '博物馆 %d 天(上限 %d)' % (ctx['museum_days'], cap)
    if dimension == 'walk_limit':
        cap = req.value.get('max_steps', 12000)
        return max(ctx['day_steps']) <= cap, '最高日约%d 步(上限 %d)' % (max(ctx['day_steps']), cap)
    if dimension == 'hot_spring':
        return ctx['has_hotspring'], '含温泉' if ctx['has_hotspring'] else '无温泉'
    if dimension == 'history':
        return ctx['has_history'], '有历史项' if ctx['has_history'] else '无历史项'
    if dimension == 'avoid_commercial':
        if not ctx['high_commercial']:
            return True, '无高商业化景点'
        return False, '含高商业化：%s' % '、'.join(ctx['high_commercial'])
    if dimension == 'pace':
        ok = max(ctx['blocks_per_day']) <= 3 and max(ctx['day_steps']) <= 20000
        return ok, '每天主项≤%d、总步数可控' % max(ctx['blocks_per_day'])
    if dimension == 'lodging':
        econ = req.value.get('economy') and ctx['lodging_pp'] <= 200
        return econ, '住宿 %d 元/人·干净安全' % ctx['lodging_pp']
    if dimension == 'weather_backup':
        return True, '该城配室内雨天备选，可一键切雨天版'
    if dimension in ('origin', 'trip_window'):
        return True, '已按设定满足'
    return True, ''     # custom 等：展示不计分


def score_plan(project, plan_ctx):
    """逐成员软偏好打分。返回 {'match':0-100, 'gaps':{member:[{dimension,why}]}}。"""
    ids = [m.id for m in project.members]
    ratios, gaps = [], {}

    def one(member_id, reqs):
        tot = met = 0
        my_gaps = []
        for r in reqs:
            if r.kind != 'soft' or r.dimension == 'custom':
                continue
            tot += r.importance
            ok, why = _soft_ok(r.dimension, r, plan_ctx)
            if ok:
                met += r.importance
            else:
                my_gaps.append({'dimension': r.dimension, 'why': why})
        return (met / float(tot)) if tot else 1.0, my_gaps

    for mid in ids:
        r, g = one(mid, project.reqs_by(mid))
        ratios.append(r)
        if g:
            gaps[mid] = g
    gr, gg = one('GROUP', project.group_reqs())
    ratios.append(gr)
    if gg:
        gaps['GROUP'] = gg
    match = int(round(100.0 * sum(ratios) / len(ratios))) if ratios else 0
    return match, gaps


# ---------------------------------------------------------------- 日程骨架
def _arrival_min(dep_min, rail_min):
    return dep_min + rail_min + TRANSFER_CITY


def _day1_blocks(cid, main_id, eve_id, dep_min, rail_min, weather):
    """Day1：出发→抵达→午餐→午后主项→晚餐→晚间可选。返回 (blocks, steps)。"""
    city = knowledge.CITIES[cid]
    blocks, steps = [], BASE_DAILY_STEPS
    arrival = _arrival_min(dep_min, rail_min)
    blocks.append({'type': 'transport', 'title': '上海 → %s' % city['name'],
                   'when': '约 %s 出发' % knowledge.fmt_min(dep_min),
                   'note': '高铁约 %d 分钟' % rail_min})
    blocks.append({'type': 'transfer', 'title': '抵达、放行李/办入住',
                   'when': '约 %s 到' % knowledge.fmt_min(arrival)})
    lunch_at = arrival + 15
    blocks.append({'type': 'lunch', 'title': '午餐（素食可选）',
                   'when': '约 %s 起' % knowledge.fmt_min(lunch_at)})

    main = _find_act(city, main_id)
    m_start = lunch_at + LUNCH_MIN + 10
    m_end = m_start + main['block_min']
    blocks.append({'type': 'activity', 'title': main['name'], 'act': main,
                   'when': '约 %s–%s' % (knowledge.fmt_min(m_start), knowledge.fmt_min(m_end)),
                   'note': main.get('desc', ''), 'cost': main.get('cost', 0)})
    steps += main['steps']
    blocks.append({'type': 'dinner', 'title': '晚餐（素食可选）',
                   'when': '约 %s 起' % knowledge.fmt_min(m_end + 10)})
    if eve_id:
        eve = _find_act(city, eve_id)
        e_start = m_end + 10 + DINNER_MIN + 10
        blocks.append({'type': 'activity', 'title': eve['name'], 'act': eve,
                       'when': '约 %s–%s' % (knowledge.fmt_min(e_start),
                                             knowledge.fmt_min(e_start + eve['block_min'])),
                       'note': eve.get('desc', ''), 'cost': eve.get('cost', 0)})
        steps += eve['steps']
    blocks.append({'type': 'hotel', 'title': '回住处休息', 'when': '晚间'})
    return blocks, steps


def _day2_blocks(cid, am_id, rail_min, last_dep_min):
    """Day2：早餐→上午主项→午餐/退房→返程。返回 (blocks, steps, dep)。"""
    city = knowledge.CITIES[cid]
    blocks, steps = [], BASE_DAILY_STEPS
    act = _find_act(city, am_id)
    blocks.append({'type': 'breakfast', 'title': '早餐', 'when': '约 8:30'})
    a_end = DEFAULT_AM_START + act['block_min']
    blocks.append({'type': 'activity', 'title': act['name'], 'act': act,
                   'when': '约 %s–%s' % (knowledge.fmt_min(DEFAULT_AM_START),
                                         knowledge.fmt_min(a_end)),
                   'note': act.get('desc', ''), 'cost': act.get('cost', 0)})
    steps += act['steps']
    blocks.append({'type': 'lunch', 'title': '午餐 / 退房寄存行李',
                   'when': '约 %s 起' % knowledge.fmt_min(a_end)})
    dep = a_end + LUNCH_MIN + TRANSFER_STATION
    blocks.append({'type': 'transport', 'title': '%s → 上海' % city['name'],
                   'when': '约 %s 发车（不晚于 %s）' % (knowledge.fmt_min(dep),
                                                       knowledge.fmt_min(last_dep_min)),
                   'note': '留足缓冲，确保 A 周日 18:00 前回到上海'})
    return blocks, steps, dep


def _rain_replace(cid, weather, act_ids):
    """雨天：把非室内项换成室内池，尽量少造第二个博物馆日。"""
    if weather != 'rain':
        return list(act_ids)
    city = knowledge.CITIES[cid]
    pool = sorted(city['rain_acts'],
                  key=lambda a: (1 if a['type'] == 'museum' else 0,
                                 -(a.get('photography', 0) * 2 + a.get('history', 0))))
    new_ids, used = [], set()
    for aid in act_ids:
        a = _find_act(city, aid)
        if a.get('indoor'):
            new_ids.append(aid)
            used.add(aid)
            continue
        repl = next((x for x in pool if x['id'] not in used), None)
        if repl is not None:
            new_ids.append(repl['id'])
            used.add(repl['id'])
        else:
            new_ids.append(aid)
    return new_ids


# ---------------------------------------------------------------- 成本
def _cost_block(project, cid, mode, lodging, act_ids):
    city = knowledge.CITIES[cid]
    meals, meals_cost = pick_meals(cid)
    lodging_pp = lodging['price_pp']
    act_cost = sum(_find_act(city, aid).get('cost', 0) for aid in act_ids)
    per_member_transport = {m.id: _person_transport_cost(project, cid, mode, m.id)
                            for m in project.members}
    # 预算口径：按"最贵成员"算（混合交通时坐高铁的人实际付得多），
    # 与冲突模块/最终账单保持一致，避免被均值掩盖。
    trans_max = max(per_member_transport.values())
    total = trans_max + lodging_pp + meals_cost + act_cost
    return {'transport': trans_max, 'lodging': lodging_pp,
            'food': meals_cost, 'activities': act_cost, 'total': total,
            'transport_by_member': per_member_transport,
            'meals': [{'kind': m['kind'], 'name': m['name'], 'cost': m['cost']}
                      for m in meals]}


# ---------------------------------------------------------------- 生成入口
def generate_plans(project, weather='sunny', max_plans=8):
    plans, city_notes = [], {}
    dep_req = project.find('depart_earliest', kind='hard')
    ret_req = project.find('return_deadline', kind='hard')
    budget_req = project.find('budget_cap')
    walk_req = project.find('walk_limit', member='C')

    dep_min = knowledge.parse_min(dep_req[0].value['time']) if dep_req else 8 * 60
    deadline_min = (knowledge.parse_min(ret_req[0].value.get('time', '18:00'))
                    if ret_req else knowledge.parse_min('18:00'))
    ret_buffer = (ret_req[0].value.get('buffer_min', knowledge.RETURN_BUFFER_MIN)
                  if ret_req else knowledge.RETURN_BUFFER_MIN)
    budget_max = budget_req[0].value.get('max_yuan') if budget_req else None
    budget_hard = bool(budget_req and budget_req[0].kind == 'hard')
    walk_max = walk_req[0].value.get('max_steps') if walk_req else None
    walk_hard = bool(walk_req and walk_req[0].kind == 'hard')

    for cid in knowledge.city_ids():
        city = knowledge.CITIES[cid]
        last_dep_min = deadline_min - city['rail_min'] - ret_buffer
        if last_dep_min < knowledge.parse_min('12:00'):
            city_notes[cid] = '按返程底线该城已无法成行（最晚发车早于中午）'
            continue
        if budget_hard and budget_max and rough_min_cost(project, cid)['total'] > budget_max:
            city_notes[cid] = '最省配置人均也超 %d 元硬预算，排除该城' % budget_max
            continue

        acts = city['acts']
        am_pool = [a for a in acts if a['slot'] in ('am', 'any')]
        pm_pool = [a for a in acts if a['slot'] in ('pm', 'any')]
        eve_pool = [a for a in acts if a['slot'] in ('eve', 'any')]
        lodging = sorted([l for l in city['lodging'] if l.get('clean_safe')],
                         key=lambda l: l['price_pp'])[0]

        for topt in transport_options(project, cid):
            for pm in pm_pool:
                for eve in eve_pool + [None]:
                    for am in am_pool:
                        chosen = [pm['id'], am['id']] + ([eve['id']] if eve else [])
                        if len(set(chosen)) != len(chosen):
                            continue                     # 同一天不重复
                        day1_ids = _rain_replace(cid, weather, [pm['id']] + ([eve['id']] if eve else []))
                        day2_ids = _rain_replace(cid, weather, [am['id']])
                        d1_blocks, d1_steps = _day1_blocks(
                            cid, day1_ids[0], day1_ids[1] if len(day1_ids) > 1 else None,
                            dep_min, city['rail_min'], weather)
                        d2_blocks, d2_steps, dep_actual = _day2_blocks(
                            cid, day2_ids[0], city['rail_min'], last_dep_min)
                        if dep_actual > last_dep_min:
                            continue                     # 返程赶不上 A 的 18:00
                        steps = [d1_steps, d2_steps]
                        if walk_hard and walk_max and max(steps) > walk_max:
                            continue
                        act_ids = [b['act']['id'] for b in d1_blocks + d2_blocks if b.get('act')]
                        costb = _cost_block(project, cid, topt['mode'], lodging, act_ids)
                        if budget_hard and budget_max and costb['total'] > budget_max:
                            continue

                        days = [
                            {'di': 1, 'label': '周六',
                             'date': project.settings.get('trip_dates', {}).get('start', ''),
                             'steps_est': d1_steps, 'blocks': d1_blocks},
                            {'di': 2, 'label': '周日',
                             'date': project.settings.get('trip_dates', {}).get('end', ''),
                             'steps_est': d2_steps, 'return_dep': dep_actual,
                             'blocks': d2_blocks},
                        ]
                        trans = {'mode': topt['mode'], 'name': topt['name'],
                                 'rail_riders': topt['rail_riders'],
                                 'car_seats': topt['car_seats'], 'note': topt['note']}

                        acts_all = [b['act'] for d in days for b in d['blocks'] if b.get('act')]
                        ctx = {
                            'total_pp': costb['total'], 'lodging_pp': costb['lodging'],
                            'day_steps': steps,
                            'museum_days': len(set(d['di'] for d in days for b in d['blocks']
                                                   if b.get('act') and b['act']['type'] == 'museum')),
                            'has_nature_photo': any(a.get('type') == 'nature' or a.get('nature', 0) >= 7
                                                    for a in acts_all),
                            'has_history': any(a.get('history', 0) >= 7 for a in acts_all),
                            'has_hotspring': any(a['type'] == 'hotspring' for a in acts_all),
                            'high_commercial': [a['name'] for a in acts_all
                                                if a.get('commercialization', 1) > 3],
                            'blocks_per_day': [len([b for b in d['blocks'] if b.get('act')])
                                               for d in days],
                        }
                        match, gaps = score_plan(project, ctx)

                        slug = '-'.join(sorted(act_ids))
                        pid = 'pl_%s_%s_%s_%s' % (cid, topt['mode'], weather, slug)
                        plan = {
                            'id': pid, 'city': cid, 'city_name': city['name'],
                            'transport': trans, 'lodging': lodging,
                            'weather': weather, 'match': match, 'gaps': gaps,
                            'cost': costb, 'days': days, 'acts_slug': slug,
                            'flags': _flags(weather, trans, acts_all, costb['total']),
                        }
                        # 独立硬约束校验（此时应为空；保证产物自洽）
                        ok, reasons = validate_plan(project, plan)
                        if not ok:
                            continue
                        plans.append(plan)
        if not any(p['city'] == cid for p in plans):
            city_notes.setdefault(cid, '该城无可行组合（试试放宽步行/预算为软约束，或换交通方式）')

    # 排序 & 择优：match 降序，同分总价升序；每城至少保 1，总量受控
    plans.sort(key=lambda p: (-p['match'], p['cost']['total'], p['city']))
    keep, seen = [], {}
    for p in plans:
        if len(keep) >= max_plans:
            break
        if seen.get(p['city'], 0) >= 2:
            continue
        keep.append(p)
        seen[p['city']] = seen.get(p['city'], 0) + 1
    return {'plans': keep, 'city_notes': city_notes, 'weather': weather}


def _flags(weather, trans, acts_all, total_pp):
    flags = []
    if any(a['type'] == 'hotspring' for a in acts_all):
        flags.append('含温泉')
    if any(a['type'] == 'museum' for a in acts_all):
        flags.append('含博物馆')
    if weather == 'rain':
        flags.append('雨天版(室内为主)')
    if trans['mode'] == 'car+rail':
        flags.append('自驾+高铁混合')
    if total_pp >= 720:
        flags.append('贴近 A 预算上限')
    return flags


# ---------------------------------------------------------------- 校验器
def validate_plan(project, plan, return_reasons=False):
    """独立硬约束校验器：产物必须通过。返回 (ok, reasons) 或 bool。"""
    reasons = []
    cid = plan['city']
    city = knowledge.CITIES[cid]
    days = plan['days']

    ret_req = project.find('return_deadline', kind='hard')
    if ret_req:
        last_dep_min = (knowledge.parse_min(ret_req[0].value.get('time', '18:00'))
                        - city['rail_min'] - ret_req[0].value.get('buffer_min', 45))
        actual = days[1].get('return_dep', 0)
        if actual and actual > last_dep_min:
            reasons.append('返程 %s 晚于最晚 %s（A 无法按时回上海）'
                           % (knowledge.fmt_min(actual), knowledge.fmt_min(last_dep_min)))
    # Day1 不早于 D 的 11:00：骨架固定 dep_min，此处防未来改坏
    dep_req = project.find('depart_earliest', kind='hard')
    if dep_req:
        first = days[0]['blocks'][0]
        if first['type'] == 'transport' and '出发' in first.get('when', ''):
            dep_str = first['when'].split('出发')[0].replace('约 ', '').strip()
            if knowledge.parse_min(dep_str) < knowledge.parse_min(dep_req[0].value['time']):
                reasons.append('Day1 出发早于 D 的最早时间')

    # 素食：午餐/晚餐块由生成器统一选素食档口（此字段供人阅读）
    # 步行 hard
    walk_req = project.find('walk_limit', member='C')
    if walk_req and walk_req[0].kind == 'hard':
        cap = walk_req[0].value['max_steps']
        if any(d['steps_est'] > cap for d in days):
            reasons.append('单日 %d 步超 C 的硬上限 %d' % (max(d['steps_est'] for d in days), cap))
    # 预算 hard
    budget_req = project.find('budget_cap')
    if budget_req and budget_req[0].kind == 'hard':
        cap = budget_req[0].value['max_yuan']
        if plan.get('cost', {}).get('total', 0) > cap:
            reasons.append('人均 %d 元超预算硬上限 %d' % (plan['cost']['total'], cap))
    # 交通：混合模式高铁人数 = 总人数 - 车座
    if plan.get('transport', {}).get('mode') == 'car+rail':
        seats = plan['transport'].get('car_seats', 4)
        riders = plan['transport'].get('rail_riders', [])
        if len(riders) != len(project.members) - seats:
            reasons.append('混合交通人数不匹配：车 %d 座 + 高铁 %d 人 ≠ %d 人'
                           % (seats, len(riders), len(project.members)))
    return (False, reasons) if reasons else (True, [])
