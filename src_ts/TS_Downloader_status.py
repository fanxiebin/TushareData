from pathlib import Path
import pandas as pd
from conf_ts.TS_API_config import pro
from conf_ts.logger_config import get_logger

# 获取logger
logger = get_logger(__name__)

def download_stock_list(output_dir: Path) -> None:
    """ 循环下载不同上市状态的股票基本信息，并拼接保存到指定目录。 """
    # 定义所有上市状态（L 为上市，D 为退市，P 为暂停上市）
    list_statuses = ['L', 'D', 'P']

    # 存储所有数据的列表
    all_data = []

    # 循环下载不同上市状态的股票信息
    for status in list_statuses:
        logger.info(f"正在下载 {status} 状态股票信息...")

        try:
            # 下载指定状态的股票基本信息
            data = pro.stock_basic(
                exchange='',  # 空字符串表示所有交易所
                list_status=status,  # 当前循环的上市状态
                fields='ts_code, name, industry, list_status, list_date, delist_date'
            )

            if not data.empty:
                logger.success(f"{status} 状态股票数量: {len(data)}")
                all_data.append(data)
            else:
                logger.warning(f"{status} 状态无数据")

        except Exception as e:
            logger.error(f"下载 {status} 状态股票信息失败: {e}")
            continue

    # 拼接所有数据并进行后续处理
    if all_data:
        # 拼接所有数据
        combined_data = pd.concat(all_data, ignore_index=True)
        logger.debug(f"总股票数量: {len(combined_data)}")

        #* 由于股票清单为一次性下载的完整数据（无需增量下载并拼接），因此下载后直接进行后续清理和调整处理
        # 后处理：过滤北交所股票（ts_code中包含"BJ"的记录）
        combined_data = combined_data[~combined_data['ts_code'].str.contains('BJ')]
        # 后处理：统一标识（部分退市股票返回的标识是d而非D，需统一为D）
        combined_data['list_status'] = combined_data['list_status'].str.replace('d', 'D')  # type: ignore
        # 后处理：按ts_code排序
        combined_data = combined_data.sort_values('ts_code').reset_index(drop=True)  # type: ignore
        # 后处理：转换日期格式
        combined_data['list_date'] = pd.to_datetime(combined_data['list_date'], format='%Y%m%d')
        combined_data['delist_date'] = pd.to_datetime(combined_data['delist_date'], format='%Y%m%d')

        stock_list_dir = output_dir / 'stock_list'
        stock_list_dir.mkdir(parents=True, exist_ok=True)
        output_path = stock_list_dir / 'current.parquet'
        combined_data.to_parquet(output_path, index=False)

        logger.success(f"完整股票清单已保存到: {output_path}")

        # 显示各状态统计信息
        status_counts = combined_data['list_status'].value_counts()
        logger.debug("各上市状态统计（不含北交所股票）:")
        for status, count in status_counts.items():
            status_name = {'L': '上市', 'D': '退市', 'P': '暂停上市'}.get(str(status), str(status))
            logger.debug(f"   {status_name}({status}): {count} 只")

    else:
        logger.error("未获取到任何股票数据")
