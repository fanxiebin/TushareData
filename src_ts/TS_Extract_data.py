import pandas as pd
from tqdm import tqdm
from tools.Utility import load_dataset_dirs_as_dict
from conf_ts.logger_config import get_logger
from conf_ts.download_config import list_load_raw, list_pivot

# 获取logger
logger = get_logger(__name__)

def align_raw(dict_raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """ 从原始数据字典读取股票和指数数据，进行数据清理、对齐 """
    #* --- 1. 数据清理 ---
    logger.debug('    股票数据清理...')
    for key in dict_raw.keys():
        # 过滤北交所股票（ts_code中包含"BJ"的记录）
        dict_raw[key] = dict_raw[key].loc[~dict_raw[key]['ts_code'].str.contains('BJ')]
        # 将ts_code和trade_date设置为索引，用于后续对齐
        dict_raw[key] = dict_raw[key].set_index(['ts_code', 'trade_date'])

    #* --- 2. 股票数据对齐 ---
    # 从raw_data_dict['daily']中提取索引作为基准，对dict_raw['adj_factor']和dict_raw['daily_basic']进行对齐
    # 由于停牌股票无价格但有复权因子，因此adj数据量较大，因此通过left方式与daily数据整合以删除
    # 由于daily_basic中较daily缺少少量日期的数据，因此通过left方式与daily数据整合并对其（缺少部分补充为nan）
    logger.debug('    股票数据对齐...')
    align_key = 'daily'
    align_index = dict_raw[align_key].index
    dict_raw = {key: df.reindex(align_index) if key != align_key else df for key, df in dict_raw.items()}

    return dict_raw

def pivot_data(df: pd.DataFrame, list_pivot: list) -> dict[str, pd.DataFrame]:
    # 计算准备
    dict_pivoted = {} # 生成输出框架
    df_cols = df.columns.tolist() # 获取数据框中的所有非索引列

    # 进行透视
    df_reset = df.reset_index() # 重置索引，将原ts_code和trade_date还原为列用于透视
    for column in set(df_cols) & set(list_pivot): # 获取需要透视的列:
        dict_pivoted[column] = df_reset.pivot(index='trade_date', columns='ts_code', values=column)
        # 将透视后的宽表的行列索引从分类数组转换为标准数据格式(string和datetime)。
        # 因为：1、pyarrow不支持分类数组；2、透视后宽表索引的重复情况消失，无需通过分类数据形式减少内存占用
        dict_pivoted[column].columns = dict_pivoted[column].columns.astype('string')
        dict_pivoted[column].index = pd.to_datetime(dict_pivoted[column].index) # 将索引转换为时间格式
    return dict_pivoted

def extract_data(dirs: dict) -> None:
    # 从各数据集目录获取所有 parquet 文件，并优化数据类型
    dict_raw = load_dataset_dirs_as_dict(dirs['raw_data'], list_load_raw)

    #* --- 1. 数据清理、对齐 ---
    logger.info('清理和对齐原始股票数据...')
    dict_align = align_raw(dict_raw)
    del dict_raw # 由于align_raw中部分操作默认为inplace，会改变dict_raw，因此需要删除

    #* --- 2. 数据透视 ---
    # 对需要透视的数据进行透视
    logger.info('透视原始股票数据...')
    dict_pivoted = {}
    for _, df in tqdm(dict_align.items(), desc='透视进度...'):
        dict_pivoted.update(pivot_data(df, list_pivot)) # 将透视后的数据更新到dict_pivoted中
    del dict_align
    logger.debug(f'透视取得 {list(dict_pivoted.keys())}')

    #* --- 3. 保存透视数据 ---
    logger.info('保存处理后的股票数据...')
    for key, df in tqdm(dict_pivoted.items(), desc='保存进度...'):
        df.to_parquet(dirs['extr_data'] / f'{key}.parquet', engine='pyarrow')

    logger.success('数据提取完成')
