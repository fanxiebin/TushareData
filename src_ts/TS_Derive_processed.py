""" 衍生层：前复权价格与其余指标宽表

close 前复权后原样落盘，停牌保持空。
价格 × (当日复权因子 / 该股最后一个非空因子)，FLOAT 链路对齐旧 pandas float32 中间值。
amount、circ_mv、turnover_rate_f 直接透出。
"""

from pathlib import Path

import duckdb
from tqdm import tqdm

from conf_ts.download_config import list_process, constant_price
from src_ts.TS_Derive_status import build_grid
from conf_ts.logger_config import get_logger

logger = get_logger(__name__)


def derive_processed(con: duckdb.DuckDBPyConnection, processed_dir: Path) -> None:
    """ 前复权（价格列）后 PIVOT 直出宽表，不做停牌填充 """
    logger.info('衍生处理后的价格与指标...')
    processed_dir.mkdir(parents=True, exist_ok=True)
    build_grid(con)

    list_adjust = set(constant_price) & set(list_process)
    for column in tqdm(sorted(list_process), desc='处理列进度...'):
        if column in list_adjust:
            # 对于需要前复权的数据，提取last_adj（该股最后一个非空因子）用于计算前复权价格
            # DuckDB ROUND 为半进位且走 DOUBLE，与 numpy 的 f32 缩放在半 way 值上有最小位级差异（已确认接受）
            from_sql = ('FROM grid g '
                        'JOIN (SELECT ts_code, arg_max(adj_factor, trade_date) AS last_adj '
                        '      FROM grid GROUP BY ts_code) la ON la.ts_code = g.ts_code')
            value_expr = (
                f'CAST(ROUND(g.{column} * CAST(g.adj_factor / la.last_adj AS FLOAT), 2) AS FLOAT)'
            )

        else:
            # 对于不需要前复权的数据，直接透出原值
            from_sql = 'FROM grid g'
            value_expr = f'g.{column}'

        con.execute(f"""
            CREATE OR REPLACE TEMP VIEW proc_{column} AS
            SELECT g.trade_date, g.ts_code, {value_expr} AS {column}
            {from_sql}
        """)
        output_path = (processed_dir / f'{column}.parquet').as_posix()
        con.execute(f"""
            COPY (
                SELECT * FROM (
                    PIVOT (SELECT trade_date, ts_code, {column} FROM proc_{column})
                    ON ts_code USING first({column})
                ) ORDER BY trade_date
            ) TO '{output_path}' (FORMAT PARQUET)
        """)
        logger.debug(f'    {column}.parquet 衍生完成')

    logger.success('处理数据衍生完成')
