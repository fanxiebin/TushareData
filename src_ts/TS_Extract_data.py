from pathlib import Path

import duckdb
from tqdm import tqdm
from conf_ts.TS_API_config import DATA_CONFIGS
from conf_ts.download_config import list_pivot
from conf_ts.logger_config import get_logger

# 获取logger
logger = get_logger(__name__)

# 透视列 -> 来源表，从DATA_CONFIGS自动推导（index_daily不参与：透视以daily为对齐基准）
COLUMN_SOURCE = {
    field: config['table']
    for config in DATA_CONFIGS.values() if config['table'] != 'index_daily'
    for field in config['fields'] if field not in ('ts_code', 'trade_date')
}

def extract_data(con: duckdb.DuckDBPyConnection, extr_dir: Path) -> None:
    """
    以daily为基准对齐各数据集（LEFT JOIN，缺失补NULL），过滤北交所股票后透视为宽表并保存parquet

    参数:
        con: DuckDB连接
        extr_dir: Path, 宽表输出目录
    """
    logger.info('透视并保存股票数据...')
    extr_dir.mkdir(parents=True, exist_ok=True)
    for column in tqdm(sorted(list_pivot), desc='透视进度...'):
        table = COLUMN_SOURCE[column]
        output_path = (extr_dir / f'{column}.parquet').as_posix() # as_posix避免Windows路径反斜杠被SQL解释为转义符
        con.execute(f"""
            COPY (
                SELECT * FROM (
                    PIVOT (
                        SELECT d.trade_date, d.ts_code, m.{column}
                        FROM daily d LEFT JOIN {table} m USING (ts_code, trade_date)
                        WHERE NOT d.ts_code LIKE '%.BJ'
                    ) ON ts_code USING first({column})
                ) ORDER BY trade_date
            ) TO '{output_path}' (FORMAT PARQUET)
        """)
        logger.debug(f'    {column}({table}表)透视完成')
    logger.success('数据提取完成')
