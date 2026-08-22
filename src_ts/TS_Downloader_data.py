import time # 导入time模块用于添加下载延迟
from datetime import datetime

import duckdb
import pandas as pd
from beartype import beartype
from beartype.vale import Is
from tqdm import tqdm
from typing import Annotated
from conf_ts.TS_API_config import DATA_CONFIGS, pro
from conf_ts.logger_config import get_logger
from tools.db import get_completed_dates

# 获取logger
logger = get_logger(__name__)

# 定义类型别名
YmdDate = Annotated[str, Is[lambda value: len(value) == 8 and value.isdigit()]]
DatasetName = Annotated[str, Is[lambda value: value in DATA_CONFIGS]]


@beartype
def download_and_save_data(con: duckdb.DuckDBPyConnection, dataset: DatasetName, download_dates: list[YmdDate]) -> None:
    """
    下载指定日期列表的数据并直接入库（数据与下载状态在同一事务中提交）

    参数:
        con: DuckDB连接
        dataset: str, 数据类型
        download_dates: list[str], 需要下载的日期列表
    """
    logger.info(f'下载{dataset}数据，共{len(download_dates)}个交易日，从{download_dates[0]}到{download_dates[-1]}')

    data_downloaded = [] # 使用列表存储各日期的数据
    status_rows: list[tuple[str, str, int, str]] = [] # (logical_date, status, row_count, message)

    # 下载数据(按日期循环下载，解决单次下载数据不超过6000条的限制）
    for date in tqdm(download_dates, desc=f'下载{dataset}数据...'):
        try:
            #! 核心下载逻辑：按dataset配置调用Tushare接口
            cur_data = DATA_CONFIGS[dataset]['download_func'](pro, date, DATA_CONFIGS[dataset]['fields'])
            logger.debug(f'    成功下载数据: {date}，共{len(cur_data)}条记录')
            if not cur_data.empty:
                # 将当前日期的数据添加到下载列表中，并记录下载成功状态信息
                data_downloaded.append(cur_data)
                status_rows.append((date, 'success', len(cur_data), ''))
            else:
                # 下载成功但数据为空，记录空数据状态信息
                status_rows.append((date, 'empty', 0, ''))
        except Exception as e:
            # 下载失败，记录失败状态信息，并使用 tqdm.write() 输出错误日志
            tqdm.write(f'ERROR: 下载数据: {date}，失败 - {str(e)}') # 使用 tqdm.write() 避免打断进度条显示
            status_rows.append((date, 'failed', 0, str(e)))
        time.sleep(0.2) # Tushare API访问频率限制为每分钟300次，无论下载成功与否，都添加0.2秒延迟，避免访问频率超限。

    # 数据与下载状态在同一事务中提交，保证两者一致
    con.execute('BEGIN TRANSACTION')
    if data_downloaded:
        data_combined = pd.concat(data_downloaded, ignore_index=True)
        # 日期列从'YYYYMMDD'字符串转为date对象（空值保持NaT，入库为NULL）
        for col in [c for c in data_combined.columns if c.endswith('date')]:
            data_combined[col] = pd.to_datetime(data_combined[col], format='%Y%m%d').dt.date

        table = DATA_CONFIGS[dataset]['table']
        columns = ', '.join(DATA_CONFIGS[dataset]['fields'])
        con.register('new_data', data_combined)
        # 主键约束在写入时去重，重复数据保留最后一次
        con.execute(f'INSERT OR REPLACE INTO {table} ({columns}) SELECT {columns} FROM new_data')
        logger.success(f'{dataset}数据入库完成: 表{table}，共{len(data_combined)}条记录')
    else:
        logger.warning(f'{dataset}本次下载无新数据入库')

    updated_at = datetime.now()
    con.executemany(
        'INSERT OR REPLACE INTO download_status VALUES (?, ?, ?, ?, ?, ?)',
        [(dataset, date, status, row_count, message, updated_at) for date, status, row_count, message in status_rows],
    )
    con.execute('COMMIT')

@beartype
def download_data(con: duckdb.DuckDBPyConnection, datasets: list[DatasetName], dates: dict[str, YmdDate]) -> None:
    """
    下载指定类型的数据并保存到数据库

    参数:
        con: DuckDB连接
        datasets: list, 要下载的数据类型列表
        dates: dict, 包含开始日期和结束日期
    """
    # 候选日期一次性构造：交易日（is_open='1'只返回交易日且按cal_date升序）；namechange可能在非交易日发布，需全部自然日
    trading_dates = pro.trade_cal(
        exchange='', start_date=dates['start'], end_date=dates['end'],
        fields='cal_date', is_open='1',
    )['cal_date'].tolist()
    natural_dates = pd.date_range(
        start=pd.to_datetime(dates['start'], format="%Y%m%d"),
        end=pd.to_datetime(dates['end'], format="%Y%m%d"),
        freq="D",
    ).strftime("%Y%m%d").tolist()

    for dataset in datasets:
        candidates = trading_dates if DATA_CONFIGS[dataset]['use_trading_calendar'] else natural_dates
        download_dates = [d for d in candidates if d not in get_completed_dates(con, dataset)] # 数据量小，循环不影响效率。

        if not download_dates:
            logger.info(f'{dataset}没有待下载日期，跳过')
        else:
            logger.info(f'{dataset}发现{len(download_dates)}个缺失日期需要下载')
            download_and_save_data(con, dataset, download_dates) # 下载数据
