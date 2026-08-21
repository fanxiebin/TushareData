""" TushareData 数据下载配置文件 """
from conf_ts.dirs_config import dirs
from tools.download_status import STATUS_FILE_NAME, get_completed_dates

def get_namechange_start_date() -> str:
    """
    从下载状态表读取 namechange 最新完成日期作为增量更新起点。
    """
    default_start = '20140101'  # 默认起始日期，文件不存在时使用
    completed_dates = get_completed_dates(dirs['raw_status'] / 'namechange' / STATUS_FILE_NAME)
    if not completed_dates:
        return default_start
    return max(completed_dates)

#* 数据下载参数
# 数据下载日期配置（验证用：仅1周）
dates_data = {'start': '20170101', 'end': '20260331'}

# 股票更名数据的日期配置（基于dates_data，但开始时间调整为更近期）
# 原则上，为保证更名期间覆盖数据期间，需扩大dates_namechange的下载时间段
# 初始化时，需将开始时间提前（如从20170101改为20140101）
# 但由于股票改名情况少，很多交易日的namechange为空数据，会被识别为需要补充而导致重复下载
# 因此增量更新时，最好将开始时间设置为较近的日期
dates_namechange = {**dates_data, 'start': get_namechange_start_date()}

# 需要下载的数据类型列表
list_data = [
    'daily',
    'adj_factor',
    'daily_basic',
    'stk_limit',
    '000001.SH',
    '399001.SZ',
    '399006.SZ'
]

# 状态数据类型列表（由于目前仅一个'namechange'状态，直接硬编码处理）
# list_status = ['namechange']

#* --- 数据提取配置 ---
#1、Extract_data参数
list_load_raw = ['adj_factor', 'daily', 'daily_basic', 'stk_limit'] # 原始数据文件名列表

#2、提取历史状态和涨跌停状态参数
constant_price = ['close', 'open', 'high', 'low'] # 常量价格数据（复权和比较股票涨跌停状态）
constant_aux = ['adj_factor', 'up_limit', 'down_limit'] # 常量辅助数据（复权和比较股票涨跌停状态使用）

#* Process_data参数
#! 需要处理的字段列表，具体处理数据的筛选逻辑请参见conf/data_config.xlsx
list_process = ['amount', 'circ_mv', 'close', 'turnover_rate_f']

# 需要复权的字段列表（自动生成），为list_process中的价格数据
list_adjust = list(set(constant_price) & set(list_process))

# 需要透视的字段列表（自动生成），为list_process和需要的辅助数据
list_pivot = list(set(constant_aux) | set(list_process) | set(constant_price))
