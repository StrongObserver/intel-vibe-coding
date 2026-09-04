# -*- coding: utf-8 -*-
"""M2 目的地知识库：为打分/生成提供"事实"，而不是拍脑袋。

每个数字都是**人工估算并标注可编辑**：它服务于"相对比较与决策讨论"，
不假装是实时 OTA/时刻表精度。结构固定，前端可增删改城市。

城市记录字段说明（tests/t_kb 会做完备性校验）：
  acts      白天可排活动；rain_acts  雨天专用的纯室内活动池；
  foods     餐饮(每顿至少一条 veg=True)；lodging 住宿(干净安全 + 经济)
  rail_min / rail_cost   上海单程高铁(分钟/元)；drive_min  自驾(分钟)
  时段语义：slot ∈ am(上午)/pm(下午)/eve(晚间/夜)；any=都可
"""
from __future__ import print_function, unicode_literals

ORIGIN = '上海'
RETURN_BUFFER_MIN = 45          # 到达上海车站后再回家的缓冲（叠加到 A 的返程截止）
BREAKFAST_COST = 15             # 每人每天早餐(酒店含早则为 0，此处为不含早兜底)

# 分钟 → "HH:MM"，供日程时间轴
def fmt_min(minutes):
    hh, mm = divmod(int(minutes) % (24 * 60), 60)
    return '%02d:%02d' % (hh, mm)

def parse_min(hhmm):
    hh, mm = hhmm.split(':')
    return int(hh) * 60 + int(mm)

def latest_rail_departure(rail_min, deadline='18:00', buffer_min=RETURN_BUFFER_MIN):
    """为保证 deadline 前回到出发地，最晚可发车时刻(门到门估算)。"""
    dep = parse_min(deadline) - rail_min - buffer_min
    if dep < 0:
        return None
    return fmt_min(dep)


CITIES = {
    'suzhou': {
        'name': '苏州', 'from_origin_km': 100,
        'rail_min': 35, 'rail_cost': 45, 'drive_min': 100,
        'rail_note': '上海虹桥→苏州，班次极密，随到随走压力小',
        'pros': '离上海最近、最省时省预算；园林/水乡/湖景齐全；回程最从容',
        'cons': '自然"大山大水"少、园林类偏精致；知名园子人多',
        'veg_note': '苏帮菜清淡，素食选择多',
        'foods': [
            {'name': '苏式汤面(全素可点)', 'kind': 'lunch', 'veg': True, 'cost': 40},
            {'name': '观前街小吃市集', 'kind': 'lunch', 'veg': False, 'cost': 35},
            {'name': '老苏州菜馆(素菜占比高)', 'kind': 'dinner', 'veg': True, 'cost': 55},
            {'name': '平江路茶馆简餐(素食友好)', 'kind': 'dinner', 'veg': True, 'cost': 50},
        ],
        'lodging': [
            {'name': '平江路附近连锁酒店', 'area': '平江路/观前街', 'price_pp': 120,
             'clean_safe': True, 'economy': True, 'from_center_min': 5, 'hot_spring': False},
            {'name': '金鸡湖畔商务酒店', 'area': '金鸡湖', 'price_pp': 180,
             'clean_safe': True, 'economy': False, 'from_center_min': 20, 'hot_spring': False},
        ],
        'acts': [
            {'id': 'sz_garden', 'name': '拙政园(园林)', 'type': 'garden',
             'slot': 'am', 'block_min': 150, 'steps': 8500, 'cost': 70,
             'photography': 8, 'nature': 7, 'history': 8, 'commercialization': 3,
             'indoor': False, 'rain': '雨天人挤，回廊可避但体验打折',
             'crowded_hot': True, 'desc': '四大名园，一步一景，摄影友好'},
            {'id': 'sz_museum', 'name': '苏州博物馆(贝聿铭)', 'type': 'museum',
             'slot': 'am', 'block_min': 120, 'steps': 5000, 'cost': 0,
             'photography': 8, 'nature': 2, 'history': 8, 'commercialization': 1,
             'indoor': True, 'crowded_hot': True, 'desc': '建筑与馆藏俱佳，雨天首选'},
            {'id': 'sz_pingjiang', 'name': '平江路历史街区', 'type': 'town',
             'slot': 'eve', 'block_min': 100, 'steps': 6000, 'cost': 0,
             'photography': 7, 'nature': 3, 'history': 8, 'commercialization': 4,
             'indoor': False, 'desc': '傍水老街，夜游出片；商业化程度中等偏上(E 会提醒)'},
            {'id': 'sz_tiger', 'name': '虎丘(云岩寺塔)', 'type': 'history',
             'slot': 'pm', 'block_min': 150, 'steps': 8000, 'cost': 60,
             'photography': 7, 'nature': 5, 'history': 9, 'commercialization': 2,
             'indoor': False, 'desc': '塔影园林，历史厚重，有坡但不大'},
            {'id': 'sz_jinji', 'name': '金鸡湖/月光码头', 'type': 'nature',
             'slot': 'eve', 'block_min': 90, 'steps': 4000, 'cost': 0,
             'photography': 9, 'nature': 7, 'history': 1, 'commercialization': 3,
             'indoor': False, 'desc': '湖景夜景+音乐喷泉(看天气)'},
        ],
        'rain_acts': [
            {'id': 'sz_museum_r', 'name': '苏州博物馆(雨天版)', 'type': 'museum',
             'block_min': 120, 'steps': 4000, 'cost': 0, 'photography': 8,
             'nature': 2, 'history': 8, 'commercialization': 1, 'indoor': True,
             'desc': '雨天室内首选'},
            {'id': 'sz_citybook', 'name': '诚品书店/苏悦广场', 'type': 'urban',
             'block_min': 90, 'steps': 3000, 'cost': 0, 'photography': 5,
             'nature': 0, 'history': 0, 'commercialization': 4, 'indoor': True,
             'desc': '商业空间，纯粹雨天兜底(E 会扣分，仅兜底用)'},
            {'id': 'sz_teahouse', 'name': '评弹茶馆(室内听曲)', 'type': 'culture',
             'block_min': 90, 'steps': 1000, 'cost': 40, 'photography': 3,
             'nature': 0, 'history': 5, 'commercialization': 3, 'indoor': True,
             'desc': '室内听评弹，有地方味'},
        ],
    },

    'hangzhou': {
        'name': '杭州', 'from_origin_km': 175,
        'rail_min': 60, 'rail_cost': 90, 'drive_min': 150,
        'rail_note': '上海虹桥→杭州东，班次多；热门日傍晚返程要早订',
        'pros': '西湖一带山水最出片，最贴合 B 的自然/摄影；植被覆盖率极高',
        'cons': '去程/返程各约 1 小时；西湖环线步行量大(对 C 需游船替代)；周末人多',
        'veg_note': '杭帮菜素食友好，寺院素斋选项多',
        'foods': [
            {'name': '楼外楼/湖畔简餐(可全素)', 'kind': 'lunch', 'veg': True, 'cost': 65},
            {'name': '龙井村农家菜(素菜现做)', 'kind': 'lunch', 'veg': True, 'cost': 55},
            {'name': '寺边素斋馆', 'kind': 'dinner', 'veg': True, 'cost': 45},
            {'name': '外婆家(家常,多点素)', 'kind': 'dinner', 'veg': False, 'cost': 50},
        ],
        'lodging': [
            {'name': '西湖边青年/经济酒店', 'area': '湖滨', 'price_pp': 150,
             'clean_safe': True, 'economy': True, 'from_center_min': 5, 'hot_spring': False},
            {'name': '武林广场地铁口连锁', 'area': '市中心', 'price_pp': 130,
             'clean_safe': True, 'economy': True, 'from_center_min': 25, 'hot_spring': False},
        ],
        'acts': [
            {'id': 'hz_westlake', 'name': '西湖苏堤/白堤散步', 'type': 'nature',
             'slot': 'am', 'block_min': 120, 'steps': 14000, 'cost': 0,
             'photography': 9, 'nature': 9, 'history': 5, 'commercialization': 3,
             'indoor': False, 'desc': '经典机位，但对 C 步行量大'},
            {'id': 'hz_boat', 'name': '西湖游船(手划/电瓶)', 'type': 'nature',
             'slot': 'any', 'block_min': 60, 'steps': 1500, 'cost': 80,
             'photography': 8, 'nature': 8, 'history': 3, 'commercialization': 3,
             'indoor': False, 'desc': '同样看景但不费腿，C 友好'},
            {'id': 'hz_lingyin', 'name': '灵隐寺/飞来峰', 'type': 'history',
             'slot': 'am', 'block_min': 150, 'steps': 9000, 'cost': 45,
             'photography': 6, 'nature': 6, 'history': 9, 'commercialization': 2,
             'indoor': False, 'desc': '古刹山林，历史感强'},
            {'id': 'hz_museum', 'name': '浙江省博物馆孤山馆', 'type': 'museum',
             'slot': 'any', 'block_min': 90, 'steps': 4000, 'cost': 0,
             'photography': 4, 'nature': 2, 'history': 8, 'commercialization': 1,
             'indoor': True, 'crowded_hot': False, 'desc': '免费室内，历史向'},
            {'id': 'hz_jiuxi', 'name': '九溪烟树', 'type': 'nature',
             'slot': 'pm', 'block_min': 120, 'steps': 11000, 'cost': 0,
             'photography': 9, 'nature': 9, 'history': 2, 'commercialization': 1,
             'indoor': False, 'desc': '溪谷森绿，最出片，但要走不少路'},
            {'id': 'hz_night', 'name': '南宋御街/河坊街夜游', 'type': 'town',
             'slot': 'eve', 'block_min': 90, 'steps': 5000, 'cost': 0,
             'photography': 5, 'nature': 0, 'history': 6, 'commercialization': 4,
             'indoor': False, 'desc': '夜游方便，商业化偏高(E 会提醒)'},
        ],
        'rain_acts': [
            {'id': 'hz_museum_r', 'name': '浙江省博物馆(雨天版)', 'type': 'museum',
             'block_min': 90, 'steps': 3000, 'cost': 0, 'photography': 4,
             'nature': 0, 'history': 8, 'commercialization': 1, 'indoor': True, 'desc': '免费室内'},
            {'id': 'hz_silk', 'name': '中国丝绸博物馆', 'type': 'museum',
             'block_min': 90, 'steps': 3000, 'cost': 0, 'photography': 6,
             'nature': 0, 'history': 6, 'commercialization': 1, 'indoor': True,
             'desc': '丝织展品+现代建筑，出片'},
            {'id': 'hz_tea', 'name': '龙井村茶室(室内品茶)', 'type': 'culture',
             'block_min': 90, 'steps': 1500, 'cost': 60, 'photography': 4,
             'nature': 4, 'history': 3, 'commercialization': 3, 'indoor': True,
             'desc': '雨天闻茶听雨'},
        ],
    },

    'nanjing': {
        'name': '南京', 'from_origin_km': 300,
        'rail_min': 90, 'rail_cost': 140, 'drive_min': 220,
        'rail_note': '上海→南京约 1.5h；周日 16:00 前后返程票偏热，务必早订',
        'pros': '历史(明+民国)+温泉(汤山)都强；同时最满足 D 和 E；物价合理',
        'cons': '距离最远、单程 1.5h，压缩 Day1 下午和 Day2 返程；A 的时间压力最大',
        'veg_note': '淮扬/南京菜素食选择多',
        'foods': [
            {'name': '南京大牌档(多点素菜)', 'kind': 'lunch', 'veg': False, 'cost': 55},
            {'name': '老门东素菜馆', 'kind': 'lunch', 'veg': True, 'cost': 50},
            {'name': '汤山温泉区简餐(素食可)', 'kind': 'dinner', 'veg': True, 'cost': 60},
            {'name': '新街口商圈家常(素)', 'kind': 'dinner', 'veg': True, 'cost': 50},
        ],
        'lodging': [
            {'name': '新街口地铁口连锁', 'area': '市中心', 'price_pp': 140,
             'clean_safe': True, 'economy': True, 'from_center_min': 10, 'hot_spring': False},
            {'name': '汤山温泉度假酒店(含泡池)', 'area': '汤山', 'price_pp': 260,
             'clean_safe': True, 'economy': False, 'from_center_min': 45, 'hot_spring': True},
        ],
        'acts': [
            {'id': 'nj_xiaoling', 'name': '明孝陵(紫金山)', 'type': 'history',
             'slot': 'am', 'block_min': 150, 'steps': 10000, 'cost': 70,
             'photography': 7, 'nature': 7, 'history': 9, 'commercialization': 2,
             'indoor': False, 'crowded_hot': True, 'desc': '世界遗产，秋色/神道出片'},
            {'id': 'nj_zhongshan', 'name': '中山陵(免费/台阶)', 'type': 'history',
             'slot': 'am', 'block_min': 120, 'steps': 9000, 'cost': 0,
             'photography': 6, 'nature': 8, 'history': 8, 'commercialization': 1,
             'indoor': False, 'desc': '392 级台阶，对腿不太友好'},
            {'id': 'nj_xuanwu', 'name': '玄武湖公园', 'type': 'nature',
             'slot': 'pm', 'block_min': 100, 'steps': 7000, 'cost': 0,
             'photography': 8, 'nature': 8, 'history': 3, 'commercialization': 2,
             'indoor': False, 'desc': '城中大湖，落日机位好'},
            {'id': 'nj_museum', 'name': '南京博物院(一院六馆)', 'type': 'museum',
             'slot': 'any', 'block_min': 150, 'steps': 6000, 'cost': 0,
             'photography': 5, 'nature': 0, 'history': 10, 'commercialization': 1,
             'indoor': True, 'crowded_hot': True, 'desc': '顶级馆藏，需预约，雨天首选'},
            {'id': 'nj_tangshan', 'name': '汤山温泉(温泉区)', 'type': 'hotspring',
             'slot': 'eve', 'block_min': 150, 'steps': 1500, 'cost': 180,
             'photography': 3, 'nature': 4, 'history': 2, 'commercialization': 3,
             'indoor': True, 'crowded_hot': True, 'desc': '泡汤解乏；晚场+往返需预留 1h+'},
            {'id': 'nj_fuzimiao', 'name': '夫子庙/秦淮河夜游', 'type': 'town',
             'slot': 'eve', 'block_min': 100, 'steps': 6000, 'cost': 0,
             'photography': 6, 'nature': 1, 'history': 7, 'commercialization': 5,
             'indoor': False, 'desc': '夜景经典但极商业化(E 会明显不满)'},
        ],
        'rain_acts': [
            {'id': 'nj_museum_r', 'name': '南京博物院(雨天版)', 'type': 'museum',
             'block_min': 150, 'steps': 5000, 'cost': 0, 'photography': 5,
             'nature': 0, 'history': 10, 'commercialization': 1, 'indoor': True,
             'crowded_hot': True, 'desc': '雨天顶级兜底'},
            {'id': 'nj_cloud', 'name': '江宁织造博物馆/六朝博物馆', 'type': 'museum',
             'block_min': 90, 'steps': 3000, 'cost': 30, 'photography': 4,
             'nature': 0, 'history': 8, 'commercialization': 1, 'indoor': True,
             'desc': '小而精'},
            {'id': 'nj_massage', 'name': '汤山温泉(雨天版)', 'type': 'hotspring',
             'block_min': 150, 'steps': 1000, 'cost': 180, 'photography': 3,
             'nature': 2, 'history': 0, 'commercialization': 3, 'indoor': True,
             'desc': '雨天泡汤，反而舒服'},
        ],
    },
}

# 城市展示顺序
CITY_ORDER = ['suzhou', 'hangzhou', 'nanjing']

# 每个城市至少应具备：素食两餐 / 住宿×2 / 白天活动 / 雨天活动 / 历史 & 自然素材
def city_ids():
    return list(CITY_ORDER)

def get_city(cid):
    return CITIES[cid]

def all_activities(cid, rain=False):
    city = CITIES[cid]
    return city['rain_acts'] if rain else city['acts']


def validate_kb():
    """知识库完备性自检：返回问题列表（空 = 通过）。测试与服务端增删改后都会调用。"""
    problems = []
    types = ('nature', 'garden', 'history', 'museum', 'hotspring', 'town', 'urban', 'culture')

    def check_int_range(rec, key, lo, hi, where):
        val = rec.get(key)
        if val is None:
            problems.append('%s 缺字段 %s' % (where, key))
            return
        if not isinstance(val, int) or isinstance(val, bool):
            problems.append('%s.%s 非整数: %r' % (where, key, val))
        elif not (lo <= val <= hi):
            problems.append('%s.%s=%s 超出 [%s,%s]' % (where, key, val, lo, hi))

    for cid in CITY_ORDER:
        city = CITIES[cid]
        where = '城市[%s]' % cid
        for key in ('rail_min', 'rail_cost', 'drive_min'):
            check_int_range(city, key, 0, 600, where)
        # 活动
        has_nature = has_history = has_rain = False
        for act in city['acts']:
            a = '活动[%s/%s]' % (cid, act.get('id'))
            if act.get('type') not in types:
                problems.append('%s.type 非法: %r' % (a, act.get('type')))
            if act.get('indoor') is True:
                has_rain = True
            if act.get('nature', 0) >= 7 or act.get('type') == 'nature':
                has_nature = True
            if act.get('history', 0) >= 7 or act.get('type') in ('history', 'museum'):
                has_history = True
            for key, lo, hi in (('block_min', 30, 240), ('steps', 0, 30000),
                                ('cost', 0, 1000), ('photography', 0, 10),
                                ('nature', 0, 10), ('history', 0, 10),
                                ('commercialization', 1, 5)):
                check_int_range(act, key, lo, hi, a)
        if not has_nature:
            problems.append('%s 缺少自然/出片素材(B 需要)' % where)
        if not has_history:
            problems.append('%s 缺少历史素材(E 需要)' % where)
        if not has_rain:
            problems.append('%s 白天活动缺少室内(雨天)项' % where)
        if len(city['rain_acts']) < 2:
            problems.append('%s 雨天活动池 <2' % where)
        # 餐饮：午/晚各至少一条 veg
        veg = {'lunch': False, 'dinner': False}
        for f in city['foods']:
            if f['kind'] not in ('lunch', 'dinner'):
                problems.append('%s foods.kind 非法: %r' % (where, f.get('kind')))
            if f.get('veg'):
                veg[f['kind']] = True
        for kind, ok in veg.items():
            if not ok:
                problems.append('%s 缺 %s 的素食选项(C 需要)' % (where, kind))
        # 住宿：至少 2 家干净安全
        econ = [l for l in city['lodging'] if l.get('clean_safe')]
        if len(econ) < 2:
            problems.append('%s 干净安全住宿 <2' % where)
        for l in city['lodging']:
            for key, lo, hi in (('price_pp', 50, 800),):
                check_int_range(l, key, lo, hi, where)
    # 城市内活动 id 唯一
    seen = set()
    for cid in CITY_ORDER:
        for act in CITIES[cid]['acts'] + CITIES[cid]['rain_acts']:
            key = (cid, act['id'])
            if key in seen:
                problems.append('活动 id 重复: %s/%s' % key)
            seen.add(key)
    return problems
