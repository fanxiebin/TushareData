""" 股票状态码唯一定义（衍生层使用，并随数据导出 status_codes.parquet 供 PyQI 读取）

状态码为字符串；None 表示非实体状态占位（名称缺失/无数据/错误状态），不会出现在宽表中。
判定规则见 src_ts/TS_Derive_status.py。
"""

#* --- 历史风险状态（ST）---
# 上市日→正常，更名公告日→名称解析状态，退市日→退市，收盘价<1元的非退市→*ST
ST_CODES = {
    '未上市': '-2',
    '正常': '0',
    'ST': '2',
    '*ST': '4',
    '退市': '6',
    '错误状态': '127',
    '名称缺失': None,
}

#* --- 涨跌停状态（全部基于收盘状态判定，up_limit=999999.999视为无限制）---
LIMIT_CODES = {
    'normal': '0',
    'up_level_1': '2',
    'up_level_2': '4',
    'up_level_3': '6',
    'down_level_1': '-2',
    'down_level_2': '-4',
    'down_level_3': '-6',
    'up_open_next': '-1',
    'down_open_next': '1',
    'no_limit': '127',
    'no_data': None,
}

#* --- 市值分层状态（流通市值横截面分位数分层，逐日计算无前瞻）---
CAP_CODES = {
    'small': '4',
    'mid': '6',
    'large': '8',
    'no_data': None,
}
CAP_LABEL_THRESHOLDS = {
    'small_quantile': 0.20,
    'large_quantile': 0.90,
}

#* --- 导出表行：(status_kind, type, code, description, buyable) ---
# buyable 为交易视角的解释属性，随码表一起导出，保证下游零拷贝
STATUS_CODE_ROWS = [
    # ST
    ('ST', '未上市', '-2', None, False),
    ('ST', '正常', '0', None, True),
    ('ST', 'ST', '2', None, True),
    ('ST', '*ST', '4', None, False),
    ('ST', '退市', '6', None, False),
    ('ST', '错误状态', '127', None, False),
    ('ST', '名称缺失', None, None, False),
    # limit
    ('limit', 'no_limit', '127', '无涨跌停限制', False),
    ('limit', 'up_level_3', '6', '一字涨停(开盘+最低+收盘)', False),
    ('limit', 'up_level_2', '4', '开盘+收盘涨停', False),
    ('limit', 'up_level_1', '2', '仅收盘涨停', False),
    ('limit', 'down_open_next', '1', '第二天跌停打开', True),
    ('limit', 'normal', '0', '正常状态', True),
    ('limit', 'up_open_next', '-1', '第二天涨停打开', True),
    ('limit', 'down_level_1', '-2', '仅收盘跌停', False),
    ('limit', 'down_level_2', '-4', '开盘+收盘跌停', False),
    ('limit', 'down_level_3', '-6', '一字跌停(开盘+最高+收盘)', False),
    ('limit', 'no_data', None, '无数据', False),
    # cap
    ('cap', 'large', '8', '大盘', True),
    ('cap', 'mid', '6', '中盘', True),
    ('cap', 'small', '4', '小盘', True),
    ('cap', 'no_data', None, '无数据', False),
]
