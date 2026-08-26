from src_ts.TS_Downloader_data import download_data
from src_ts.TS_Downloader_status import download_stock_list
from src_ts.TS_Derive_status import derive_status
from src_ts.TS_Derive_processed import derive_processed
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

    #%% --- 数据衍生 ---
    #* 一、生成ST/涨跌停/市值分层状态宽表与状态码表（原PyQI侧TS_Extract_status迁移至此，
    #     旧提取层1_extracted_data已无消费者，随迁移归档至_legacy）
    logger.info("开始衍生状态数据...")
    derive_status(con, dirs['extr_status'])

    #* 二、价格前复权与停牌填充，产出下游直接可用的数据（原PyQI侧TS_Processer_data迁移至此）
    logger.info("开始衍生处理后的数据...")
    derive_processed(con, dirs['processed'])
finally:
    con.close()

logger.success("TushareData 数据下载和提取流程全部完成！")
