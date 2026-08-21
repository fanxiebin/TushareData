from src_ts.TS_Downloader_data import download_data
from src_ts.TS_Downloader_status import download_stock_list
from src_ts.TS_Extract_data import extract_data
from tools.Utility import backup_directory
from conf_ts.logger_config import get_logger
from conf_ts.dirs_config import dirs, init_dirs
from conf_ts.download_config import dates_data, dates_namechange, list_data

logger = get_logger(__name__)
init_dirs()

#%% --- 备份文件 ---
logger.info("开始备份数据目录...")
backup_directory(dirs['raw_data'], dirs['backup'])
backup_directory(dirs['raw_status'], dirs['backup'])

#%% --- 股票数据和状态信息下载 ---
# 此部分的功能仅限更新下载的原始数据，不进行任何格式转换和处理
logger.info("开始下载股票数据...")
download_data(list_data, dates_data, dirs['raw_data'])

logger.info("开始下载股票状态...")
download_stock_list(dirs['raw_status']) # 默认下载当日的最新信息（无需下载参数，默认下载当前最新股票清单）
download_data(['namechange'], dates_namechange, dirs['raw_status'])

#%% --- 数据提取 ---
#* 一、从dir_raw获取原始数据，进行对齐和透视，并保存到extracted_data目录
logger.info("开始提取和透视原始股票数据...")
extract_data(dirs)

logger.success("TushareData 数据下载和提取流程全部完成！")
