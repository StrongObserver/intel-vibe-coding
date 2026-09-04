# -*- coding: utf-8 -*-
"""M5c 决策总结导出：把"选定方案 + 逐人表态 + 待确认"编译成可直接发群聊的文本。

这是"从讨论到拍板"的最后一公里：可读、可转发、把责任/截止时间写清楚。
"""
from __future__ import print_function, unicode_literals

VOTE_LABEL = {'accept': '✓ 接受', 'concerned': '▲ 有保留', 'oppose': '✗ 反对'}


def _cost_line(cost):
    return ('人均约 %d 元 = 交通 %d(按坐高铁者口径) + 住宿 %d + 餐饮 %d + 门票活动 %d'
            % (cost['total'], cost['transport'], cost['lodging'], cost['food'],
               cost['activities']))


def find_plan(result, plan_id):
    for p in result.get('plans', []):
        if p['id'] == plan_id:
            return p
    raise ValueError('找不到方案：%s' % plan_id)


def build_export(project, result, plan_id, votes=None, members=None):
    """编译定稿文本。votes: {成员: 'accept'|'concerned'|'oppose'}。"""
    plan = find_plan(result, plan_id)
    votes = votes or {}
    city = plan['city_name']
    dates = project.settings.get('trip_dates', {})
    lines = []
    ap = lines.append

    ap('======== 周末两天一夜 · 旅行方案 ========')
    ap('目的地：%s｜%s～%s' % (city, dates.get('start', '?'), dates.get('end', '?')))
    ap('交通：%s' % plan['transport']['name'])
    if plan['transport'].get('note'):
        ap('　└ %s' % plan['transport']['note'])
    ap('住宿：%s（%d 元/人·夜，干净安全）' % (plan['lodging']['name'],
                                           plan['lodging']['price_pp']))
    if plan['weather'] == 'rain':
        ap('天气预案：本版为【雨天版】，全部活动已换室内，雨天照走。')
    ap('')
    ap('-------- 行程 --------')
    for d in plan['days']:
        ap('◆ %s %s' % (d['label'], d.get('date', '')))
        for b in d['blocks']:
            head = '　%s %s %s' % (b.get('when', ''), b.get('title'), b.get('note', ''))
            ap(head.rstrip())
        ap('　（当日步行约 %d 步）' % d['steps_est'])
    ap('')
    ap('-------- 费用 --------')
    ap(_cost_line(plan['cost']))
    ap('')

    # 逐人核对（综合 gaps 与硬约束）
    ap('-------- 逐人核对 --------')
    _members = members if members is not None else [m.id for m in project.members]
    ok_lines, bad_lines = [], []
    for mid in _members:
        gap_list = plan.get('gaps', {}).get(mid, [])
        if gap_list:
            detail = '；'.join(g['why'] for g in gap_list)
            bad_lines.append('%s：未完全满足 → %s' % (mid, detail))
        else:
            ok_lines.append(mid)
    if ok_lines:
        ap('✓ 无缺口：%s' % '、'.join(ok_lines))
    for x in bad_lines:
        ap('○ %s' % x)
    ap('')

    # 表态结果（即使还没人表态也如实呈现）
    if votes is not None:
        ap('-------- 群内表态 --------')
        for mid in _members:
            st = votes.get(mid)
            if st:
                ap('%s：%s' % (mid, VOTE_LABEL.get(st, st)))
            else:
                ap('%s：— 未表态' % mid)
        agreed = [m for m in _members if votes.get(m) == 'accept']
        ap('已明确接受：%s' % ('、'.join(agreed) if agreed else '(还没有人表态)'))
        ap('')

    ap('-------- 拍板前待确认 / 待办（谁 · 何时）--------')
    return lines


def build_open_questions(analysis):
    """把不确定性账本转成简洁两栏待办。analysis = analyze_project() 结果。"""
    out = []
    for u in analysis['uncertainties']:
        due = '（%s）' % u['due'] if u.get('due') else ''
        out.append('□ %s → %s %s' % (u['question'], u['owner'], due))
    return out


def finalize_text(project, result, plan_id, votes=None,
                  conflicts_res=None, members=None):
    """汇总最终文本：定稿方案 + 待确认清单。"""
    lines = build_export(project, result, plan_id, votes=votes, members=members)
    lines.append('□ 请务必在群里敲定以下事项：')
    lines.extend(build_open_questions(conflicts_res or {'uncertainties': []}))
    lines.append('')
    lines.append('（本方案由六人决策工作台生成；金额/时间为估算，订票订房前请复核）')
    return '\n'.join(lines)
