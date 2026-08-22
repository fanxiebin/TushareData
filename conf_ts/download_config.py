""" TushareData 数据下载配置文件 """
import duckdb

from conf_ts.dirs_config import db_path
from tools.db import get_completed_dates

def get_namechange_start_date() -> str:
    """
    从数据库下载状态表读取 namechange 最新完成日期作为增量更新起点。
    """
    if not db_path.exists():
        return '20140101'  # 默认起始日期，数据库文件不存在时使用（首次初始化场景）
    con = duckdb.connect(str(db_path), read_only=True)
    completed_dates = get_completed_dates(con, 'namechange')
    con.close()
    return max(completed_dates) if completed_dates else '20140101'

#* 数据下载参数
# 数据下载日期配置
dates_data = {'start': '20170101', 'end': '20260331'}

# 股票更名数据的日期配置（基于dates_data，但开始时间调整为更近期）
# 原则上，为保证更名期间覆盖数据期间，需扩大dates_namechange的下载时间段
# 初始化时，需将开始时间提前（如从20170101改为20140101）
# 但由于股票改名情况少，很多交易日的namechange为空数据，会被识别为需要补充而导致重复下载
# 因此增量更新时，最好将开始时间设置为较近的日期
dates_namechange = {**dates_data, 'start': get_namechange_start_date()}

# 需要下载的数据类型列表
datasets = [
    'daily',
    'adj_factor',
    'daily_basic',
    'stk_limit',
    '000001.SH',
    '399001.SZ',
    '399006.SZ'
]

# 状态数据：仅'namechange'一种，update_main.py中硬编码处理，无需配置列表

#* --- 数据透视配置（供 TS_Extract_data 使用） ---
# 常量价格数据（复权和比较股票涨跌停状态）
constant_price = ['close', 'open', 'high', 'low']
# 常量辅助数据（复权和比较股票涨跌停状态使用）
constant_aux = ['adj_factor', 'up_limit', 'down_limit']

# 需要透视的字段列表（自动生成），为处理目标字段和需要的辅助数据
list_process = ['amount', 'circ_mv', 'close', 'turnover_rate_f']
list_pivot = list(set(constant_aux) | set(list_process) | set(constant_price))
