# -*- coding: utf-8 -*-
"""需求领域模型。

把"六人两天一夜"决策问题建模为：
  Project(项目) ──> Member(成员) ──> Requirement(一条硬约束/偏好)
                    + Settings(行程设置与假设)

核心设计决策：
* 一条需求 = dimension(维度) + kind(hard=硬约束 / soft=偏好) + value(结构化取值)
  + quote(群聊原文，可追溯) + note(我们为什么这样判，可修改)。
* 判定"硬 / 软"依据群聊语气词：必须/最快…才能/只能 = hard；
  最好/不想/比较想/希望 = soft。人工可在 UI 上随时翻转并改 note。
* 所有数据可序列化为 JSON 以便前端读写与保存。
"""
from __future__ import print_function

# ---------------------------------------------------------------------------
# 维度注册表：每种维度声明了它关心的 value 字段与校验规则，
# 供引擎 / 前端 / 测试三方共用，避免到处散落 magic string。
# ---------------------------------------------------------------------------
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')

# value_schema: {字段名: (类型, 说明)}；'*' 表示必填。这里用于友好校验。
DIMENSION_SCHEMAS = {
    'budget_cap': {
        'label': '预算上限',
        'value': {'max_yuan': ('int', '每人预算上限(元)', '*'), 'unit': ('str', '口径：person=每人 / trip=整趟', '*')},
    },
    'return_deadline': {
        'label': '返程截止(硬)',
        'value': {'day': ('str', '周几，如 sunday', '*'), 'place': ('str', '回到哪座城市', '*'),
                  'time': ('str', 'HH:MM 截止时间', '*'), 'buffer_min': ('int', '到家/取行李等缓冲分钟', '')},
    },
    'depart_earliest': {
        'label': '最早出发时间(硬)',
        'value': {'day': ('str', '周几，如 saturday', '*'), 'time': ('str', 'HH:MM 最早出发', '*')},
    },
    'diet': {
        'label': '饮食',
        'value': {'type': ('str', 'vegetarian=素食 / vegan / halal / none', '*')},
    },
    'walk_limit': {
        'label': '单日步行上限',
        'value': {'max_steps': ('int', '每天最多步数', '*')},
    },
    'hot_spring': {
        'label': '温泉需求',
        'value': {'want': ('bool', '是否希望安排温泉', '')},
    },
    'nature_photo': {
        'label': '自然风景 / 拍照',
        'value': {'importance': ('int', '1-5', '')},
    },
    'history': {
        'label': '历史感',
        'value': {'importance': ('int', '1-5', '')},
    },
    'avoid_commercial': {
        'label': '反商业化',
        'value': {'max_level': ('int', '可接受的商业化程度 1-5', '')},
    },
    'museum_avoid': {
        'label': '避免整天泡博物馆',
        'value': {'max_museum_days': ('int', '全程最多几个全天博物馆', '')},
    },
    'transport_capacity': {
        'label': '交通载客能力(硬事实)',
        'value': {'driver': ('str', '开车的人', '*'), 'seats': ('int', '含驾驶员座位数', '*'),
                  'can_rail': ('bool', '是否可坐高铁', '')},
    },
    'pace': {
        'label': '行程松紧',
        'value': {'relaxed': ('bool', '是否希望宽松不赶', '')},
    },
    'lodging': {
        'label': '住宿要求',
        'value': {'clean_safe': ('bool', '干净安全优先', ''), 'economy': ('bool', '不需要豪华', '')},
    },
    'weather_backup': {
        'label': '天气备选',
        'value': {'indoor_plan': ('bool', '天气不好时有室内替代', '')},
    },
    'origin': {
        'label': '出发地假设',
        'value': {'city': ('str', '出发城市(默认上海)', '*')},
    },
    'trip_window': {
        'label': '行程时间窗',
        'value': {'nights': ('int', '过夜数(=1)', '*'), 'start_day': ('str', '周几', ''),
                  'end_day': ('str', '周几', '')},
    },
    'custom': {
        'label': '其他',
        'value': {'text': ('str', '自由描述，仅供展示与讨论', '')},
    },
}

VALID_DIMENSIONS = tuple(DIMENSION_SCHEMAS.keys())
VALID_KINDS = ('hard', 'soft')

# 建议的默认硬/软（供 UI 与种子需求使用，人工可覆盖）
DEFAULT_KIND_BY_DIMENSION = {
    'return_deadline': 'hard',
    'depart_earliest': 'hard',
    'diet': 'hard',
    'transport_capacity': 'hard',
    'budget_cap': 'soft',
    'walk_limit': 'soft',
    'hot_spring': 'soft',
    'nature_photo': 'soft',
    'history': 'soft',
    'avoid_commercial': 'soft',
    'museum_avoid': 'soft',
    'pace': 'soft',
    'lodging': 'soft',
    'weather_backup': 'soft',
    'origin': 'soft',
    'trip_window': 'soft',
    'custom': 'soft',
}


def _check_time(value):
    parts = value.split(':')
    if len(parts) != 2:
        raise ValueError('时间格式须为 HH:MM：%r' % value)
    hh, mm = parts
    if not (hh.isdigit() and mm.isdigit()):
        raise ValueError('时间格式须为 HH:MM：%r' % value)
    hh, mm = int(hh), int(mm)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError('时间超出范围：%r' % value)


def validate_value(dimension, value):
    """按维度 schema 校验 value。返回清洗后的 value（补默认、报错带中文信息）。"""
    if dimension not in DIMENSION_SCHEMAS:
        raise ValueError('未知需求维度：%r' % dimension)
    schema = DIMENSION_SCHEMAS[dimension]['value']
    cleaned = {}
    for key, (typ, _desc, required) in schema.items():
        if key in value and value[key] is not None:
            cleaned[key] = value[key]
        elif required == '*':
            raise ValueError('维度 %s 缺少必填字段 %r' % (dimension, key))
    for key, val in cleaned.items():
        typ = schema[key][0]
        if typ == 'int' and not isinstance(val, bool) and isinstance(val, int):
            if dimension == 'budget_cap' and key == 'max_yuan' and val <= 0:
                raise ValueError('预算必须 > 0')
            if dimension == 'walk_limit' and key == 'max_steps' and val <= 0:
                raise ValueError('步行上限必须 > 0')
            continue
        if typ == 'int':
            # 允许数字字符串
            try:
                cleaned[key] = int(val)
            except (TypeError, ValueError):
                raise ValueError('字段 %s.%s 需要是整数，得到 %r' % (dimension, key, val))
            continue
        if typ == 'str' and not isinstance(val, str):
            raise ValueError('字段 %s.%s 需要是字符串，得到 %r' % (dimension, key, val))
        if typ == 'bool':
            if isinstance(val, bool):
                continue
            if val in (0, 1, '0', '1', 'true', 'false', 'True', 'False'):
                cleaned[key] = val in (1, '1', 'true', 'True')
                continue
            raise ValueError('字段 %s.%s 需要是布尔，得到 %r' % (dimension, key, val))
    # 时间类字段做格式校验
    if dimension in ('return_deadline', 'depart_earliest'):
        for key in ('time',):
            if key in cleaned:
                _check_time(cleaned[key])
        if 'day' in cleaned and cleaned['day'] not in WEEKDAYS:
            raise ValueError('字段 %s.day 需要是 %s 之一' % (dimension, ','.join(WEEKDAYS)))
    return cleaned


class Requirement(object):
    """一条需求：硬约束(hard)或偏好(soft)。"""

    __slots__ = ('rid', 'scope', 'member', 'dimension', 'kind', 'importance',
                 'value', 'quote', 'note')

    def __init__(self, dimension, scope='group', member=None, kind=None,
                 value=None, quote='', note='', importance=3, rid=None):
        self.dimension = dimension
        if dimension not in DIMENSION_SCHEMAS:
            raise ValueError('未知需求维度：%r' % dimension)
        if scope not in ('member', 'group'):
            raise ValueError('scope 须为 member 或 group')
        if scope == 'member' and not member:
            raise ValueError('member 范围的约束必须指定 member')
        if scope == 'group' and member:
            raise ValueError('group 范围约束不应绑定 member=%r，会丢失归属' % member)
        if member and (len(member) != 1 or not member.isupper()):
            raise ValueError('member 须为大写字母 A-Z，得到 %r' % member)
        self.scope = scope
        self.member = member if scope == 'member' else None
        self.kind = kind if kind else DEFAULT_KIND_BY_DIMENSION.get(dimension, 'soft')
        if self.kind not in VALID_KINDS:
            raise ValueError('kind 须为 hard/soft，得到 %r' % self.kind)
        self.importance = int(importance)
        if not (1 <= self.importance <= 5):
            raise ValueError('importance 须在 1-5')
        self.value = validate_value(dimension, value or {})
        self.quote = quote or ''
        self.note = note or ''
        self.rid = rid or self._default_rid()

    def _default_rid(self):
        head = self.member or 'GROUP'
        return '%s_%s_%s' % (head, self.dimension, id(self) % 100000)

    @property
    def is_hard(self):
        return self.kind == 'hard'

    @property
    def owner_label(self):
        return ('全员' if self.scope == 'group' else '成员 ' + self.member)

    def to_dict(self):
        return {
            'rid': self.rid, 'scope': self.scope, 'member': self.member,
            'dimension': self.dimension, 'kind': self.kind,
            'importance': self.importance, 'value': dict(self.value),
            'quote': self.quote, 'note': self.note,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            dimension=data['dimension'], scope=data.get('scope', 'group'),
            member=data.get('member'), kind=data.get('kind'),
            value=data.get('value', {}), quote=data.get('quote', ''),
            note=data.get('note', ''), importance=data.get('importance', 3),
            rid=data.get('rid'),
        )

    def __repr__(self):
        return '<Req %s %s[%s] %s>' % (self.dimension, self.kind,
                                       self.owner_label, self.value)


class Member(object):
    __slots__ = ('id', 'alias', 'note')

    def __init__(self, member_id, alias='', note=''):
        if len(member_id) != 1 or not member_id.isupper():
            raise ValueError('member id 须为大写字母')
        self.id = member_id
        self.alias = alias or ''
        self.note = note or ''

    def to_dict(self):
        return {'id': self.id, 'alias': self.alias, 'note': self.note}

    @classmethod
    def from_dict(cls, data):
        return cls(data['id'], alias=data.get('alias', ''), note=data.get('note', ''))

    def __repr__(self):
        return '<Member %s %s>' % (self.id, self.alias)


class Project(object):
    """一个项目 = 成员 + 行程设置/假设 + 所有需求（统一列表，便于展示）。"""

    def __init__(self, members=None, requirements=None, settings=None):
        self.members = members or []
        self.requirements = requirements or []  # list[Requirement]
        self.settings = settings or {}

    # -- 派生查询 ----------------------------------------------------------
    def member_ids(self):
        return [m.id for m in self.members]

    def reqs_by(self, member_id):
        return [r for r in self.requirements if r.member == member_id]

    def group_reqs(self):
        return [r for r in self.requirements if r.scope == 'group']

    def find(self, dimension, member=None, kind=None):
        out = []
        for r in self.requirements:
            if r.dimension != dimension:
                continue
            if member and r.member != member:
                continue
            if kind and r.kind != kind:
                continue
            out.append(r)
        return out

    def add(self, requirement):
        self.requirements.append(requirement)

    def remove(self, rid):
        self.requirements = [r for r in self.requirements if r.rid != rid]

    # -- 序列化 ------------------------------------------------------------
    def to_dict(self):
        return {
            'members': [m.to_dict() for m in self.members],
            'requirements': [r.to_dict() for r in self.requirements],
            'settings': self.settings,
        }

    @classmethod
    def from_dict(cls, data):
        members = [Member.from_dict(x) for x in data.get('members', [])]
        requirements = [Requirement.from_dict(x) for x in data.get('requirements', [])]
        return cls(members=members, requirements=requirements,
                   settings=data.get('settings', {}))

    def __repr__(self):
        return '<Project members=%s reqs=%d>' % (self.member_ids(),
                                                 len(self.requirements))
