""" TushareData 目录配置文件 """
import os
import warnings
from pathlib import Path

# 仓库根目录 = conf_ts/ 的上一级（相对定位，克隆到任意路径均可运行）
dir_root = Path(__file__).resolve().parent.parent

# 数据根目录：默认在 TUSHARE_DATA_DIR 环境变量指定的路径下，若未设置则发出警告
if os.environ.get('TUSHARE_DATA_DIR'):
    data_root = Path(os.environ['TUSHARE_DATA_DIR'])
else:
    warnings.warn("未设置环境变量 TUSHARE_DATA_DIR，回退到仓库内的 data 目录")
    data_root = dir_root / 'data' # 必须设置回退目录，否则后续pylance会报警

# DuckDB数据库文件路径
db_path = data_root / 'tushare.duckdb'

dirs = {
    'extr_status': data_root / '1_extracted_status',
    'processed': data_root / '2_processed',
    'backup': data_root / 'SS',
}
