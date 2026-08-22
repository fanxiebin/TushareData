from src_ts.TS_Downloader_data import download_data
from src_ts.TS_Downloader_status import download_stock_list
from src_ts.TS_Extract_data import extract_data
from tools.db import connect, backup_database
from conf_ts.logger_config import get_logger
from conf_ts.dirs_config import dirs, db_path
from conf_ts.download_config import dates_data, dates_namechange, datasets

logger = get_logger(__name__)

#%% --- 备份数据库（需在建立连接前完成文件拷贝） ---
logger.info("开始备份数据库...")
backup_database(db_path, dirs['backup'])

con = connect(db_path)
try:
    #%% --- 股票数据和状态信息下载 ---
    # 此部分的功能仅限更新下载的原始数据，不进行任何格式转换和处理
    logger.info("开始下载股票数据...")
    download_data(con, datasets, dates_data)

    logger.info("开始下载股票状态...")
    download_stock_list(con) # 默认下载当日的最新信息（无需下载参数，默认下载当前最新股票清单）
    download_data(con, ['namechange'], dates_namechange)

    #%% --- 数据提取 ---
    #* 一、以daily为基准对齐各数据集，透视为宽表并保存到extracted_data目录
    logger.info("开始提取和透视原始股票数据...")
    extract_data(con, dirs['extr_data'])
finally:
    con.close()

logger.success("TushareData 数据下载和提取流程全部完成！")
