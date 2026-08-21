import pandas as pd
import time # 导入time模块用于添加下载延迟
from beartype import beartype
from beartype.vale import Is
from pathlib import Path # 导入Path用于文件路径操作
from tqdm import tqdm
from typing import Annotated
from conf_ts.TS_API_config import DATA_CONFIGS, pro
from conf_ts.logger_config import get_logger
from tools.download_status import STATUS_FILE_NAME, get_completed_dates, upsert_status_entries

# 获取logger
logger = get_logger(__name__)

# 定义类型别名
YmdDate = Annotated[str, Is[lambda value: len(value) == 8 and value.isdigit()]]
DatasetName = Annotated[str, Is[lambda value: value in DATA_CONFIGS]]


@beartype
def download_single_date(item: DatasetName, date: YmdDate) -> pd.DataFrame:
    """ 下载单个日期的数据 """
    # 读取输入待下载数据（item）的下载参数
    download_func = DATA_CONFIGS[item]['download_func']
    download_fields = DATA_CONFIGS[item]['fields']

    cur_data = download_func(pro, date, download_fields) # !核心下载逻辑
    logger.debug(f'    成功下载数据: {date}，共{len(cur_data)}条记录')

    return cur_data

@beartype
def download_and_save_data(item: DatasetName, download_dates: list[YmdDate], dataset_dir: Path) -> None:
    """
    下载指定日期列表的数据并保存到指定文件

    参数:
        item: str, 数据类型
        download_dates: list[str], 需要下载的日期列表
        dataset_dir: Path, 数据集目录
    """
    status_file = dataset_dir / STATUS_FILE_NAME
    logger.info(f'下载{item}数据，共{len(download_dates)}个交易日，从{download_dates[0]}到{download_dates[-1]}')

    data_downloaded = [] # 使用列表存储各日期的数据
    status_rows_by_date: dict[str, dict[str, str | int]] = {}

    # 下载数据(按日期循环下载，解决单次下载数据不超过6000条的限制）
    for date in tqdm(download_dates, desc=f'下载{item}数据...'):
        try:
            cur_data = download_single_date(item, date) #! 核心下载逻辑
            if not cur_data.empty:
                # 将当前日期的数据添加到下载列表中，并记录下载成功状态信息
                data_downloaded.append(cur_data)
                status_rows_by_date[date] = {
                    'logical_date': date,
                    'status': 'success',
                    'row_count': len(cur_data),
                    'message': '',
                }
            else:
                # 下载成功但数据为空，记录空数据状态信息
                status_rows_by_date[date] = {
                    'logical_date': date,
                    'status': 'empty',
                    'row_count': 0,
                    'message': '',
                }
        except Exception as e:
            # 下载失败，记录失败状态信息，并使用 tqdm.write() 输出错误日志
            tqdm.write(f'ERROR: 下载数据: {date}，失败 - {str(e)}') # 使用 tqdm.write() 避免打断进度条显示
            status_rows_by_date[date] = {
                'logical_date': date,
                'status': 'failed',
                'row_count': 0,
                'message': str(e),
            }
        time.sleep(0.2) # Tushare API访问频率限制为每分钟300次，无论下载成功与否，都添加0.2秒延迟，避免访问频率超限。

    if data_downloaded:
        data_combined = pd.concat(data_downloaded, ignore_index=True)
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        delta_path = dataset_dir / f'delta_{timestamp}.parquet'
        data_combined.to_parquet(delta_path, engine='pyarrow', index=False)
        logger.success(f'原始{item}数据保存完成: {delta_path.name}，共{len(data_combined)}条记录')
    else:
        logger.warning(f'下载数据为空，无需更新')


    if status_rows_by_date:
        upsert_status_entries(status_file, list(status_rows_by_date.values()))

@beartype
def download_data(list_download: list[DatasetName], dates: dict[str, YmdDate], dir_output: Path) -> None:
    """
    下载指定类型的数据并保存到硬盘

    参数:
        list_download: list, 要下载的数据类型列表
        dates: dict, 包含开始日期和结束日期
        dir_output: Path, 数据保存目录
    """
    # 在循环外部初始化交易日历，提升效率
    trading_calendar = pro.trade_cal(exchange='', start_date=dates['start'], end_date=dates['end'], fields='cal_date', is_open='1')
    trading_dates: set[YmdDate] = set(trading_calendar['cal_date'].tolist())

    for item in list_download:
        # 验证数据目录，并获取下载状态文件路径
        dataset_dir = dir_output / item
        dataset_dir.mkdir(parents=True, exist_ok=True)
        status_file = dataset_dir / STATUS_FILE_NAME

        # 检查是否需要下载新数据
        if not DATA_CONFIGS[item]['use_trading_calendar']:
            # 由于namechange数据可能在非交易日发布，因此下载日期为所有日期。
            calendar_dates = pd.date_range(
                start=pd.to_datetime(dates['start'], format="%Y%m%d"),
                end=pd.to_datetime(dates['end'], format="%Y%m%d"),
                freq="D"
            ).strftime("%Y%m%d").tolist()
            download_dates = sorted(set(calendar_dates) - get_completed_dates(status_file))
        else:
            # daily，adj_factor等其他数据仅在交易日发布，因此按照交易日下载
            download_dates = sorted(trading_dates - get_completed_dates(status_file))

        # 检查是否有需要下载的日期（如果download_dates或trading_dates为空集，则此时差集download_dates为空集）
        if not download_dates:
            logger.info(f'{item}没有待下载日期，跳过')
        else:
            logger.info(f'{item}发现{len(download_dates)}个缺失日期需要下载')
            download_and_save_data(item, download_dates, dataset_dir) # 下载数据
