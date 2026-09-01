""" TushareData 目录配置文件 """

from pathlib import Path

# 仓库根目录 = conf_ts/ 的上一级（相对定位，克隆到任意路径均可运行）
dir_root = Path(__file__).resolve().parent.parent

# DuckDB数据库文件路径
db_path = dir_root / 'data/tushare.duckdb'

dirs = {
    'extr_status': dir_root / 'data/1_extracted_status',
    'processed': dir_root / 'data/2_processed',
    'backup': dir_root / 'data/SS',
}
