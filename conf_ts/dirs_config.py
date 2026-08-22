""" TushareData 目录配置文件 """

from pathlib import Path

dir_root = Path('C:/Users/neilf/Documents/GitHub/TushareData')

# DuckDB数据库文件路径
db_file = dir_root / 'data/tushare.duckdb'

dirs = {
    'extr_data': dir_root / 'data/1_extracted_data',
    'backup': dir_root / 'data/SS',
}
