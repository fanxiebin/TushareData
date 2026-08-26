""" 衍生层：价格前复权与停牌填充，产出下游直接可用的 processed 宽表

替代原PyQI侧TS_Processer_data.py的pandas后处理，全部在DuckDB内完成：
- 前复权：价格 × (当日复权因子 / 该股最后一个非空因子)，FLOAT链路对齐旧pandas float32中间值
- 停牌填充：ffill(limit=10, limit_area='inside')语义，即仅在前后都有真实值的内部缺口内，
  向前填充最多10个交易日（体现停牌期间价格不变的实质）
"""

from pathlib import Path

import duckdb
from tqdm import tqdm

from conf_ts.download_config import list_process, constant_price
from src_ts.TS_Derive_status import build_grid
from conf_ts.logger_config import get_logger

logger = get_logger(__name__)


def derive_processed(con: duckdb.DuckDBPyConnection, processed_dir: Path) -> None:
    """ 对list_process各列做前复权（价格类）与停牌填充，PIVOT直出宽表parquet """
    logger.info('衍生处理后的价格与指标数据（前复权+停牌填充）...')
    processed_dir.mkdir(parents=True, exist_ok=True)
    build_grid(con)

    list_adjust = set(constant_price) & set(list_process)  # 需要复权的价格类字段
    for column in tqdm(sorted(list_process), desc='复权填充进度...'):
        if column in list_adjust:
            # 前复权并先行取整（与旧pandas在复权步round(2)一致），last_adj为该股最后一个非空因子。
            # DuckDB ROUND为半进位且走DOUBLE，与numpy的f32缩放路径在半way值/大数值上存在最小位级差异（已确认接受）
            value_expr = (
                f'CAST(ROUND(g.{column} * CAST(g.adj_factor / la.last_adj AS FLOAT), 2) AS FLOAT)'
            )
            from_sql = ('FROM grid g '
                        'JOIN (SELECT ts_code, arg_max(adj_factor, trade_date) AS last_adj '
                        '      FROM grid GROUP BY ts_code) la ON la.ts_code = g.ts_code')
        else:
            value_expr = f'g.{column}'
            from_sql = 'FROM grid g'

        con.execute(f"""
            CREATE OR REPLACE TEMP VIEW proc_{column} AS
            SELECT trade_date, ts_code,
                   CAST(ROUND(
                       CASE WHEN x IS NOT NULL THEN x
                            WHEN first_value(x IGNORE NULLS) OVER wf IS NOT NULL
                            THEN last_value(x IGNORE NULLS) OVER wb
                       END, 2) AS FLOAT) AS {column}
            FROM (SELECT g.trade_date, g.ts_code, {value_expr} AS x {from_sql}) t
            WINDOW wf AS (PARTITION BY ts_code ORDER BY trade_date
                          ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING),
                   wb AS (PARTITION BY ts_code ORDER BY trade_date
                          ROWS BETWEEN 10 PRECEDING AND CURRENT ROW)
        """)

        output_path = (processed_dir / f'{column}.parquet').as_posix()  # as_posix避免Windows反斜杠被SQL解释为转义符
        con.execute(f"""
            COPY (
                SELECT * FROM (
                    PIVOT (SELECT trade_date, ts_code, {column} FROM proc_{column})
                    ON ts_code USING first({column})
                ) ORDER BY trade_date
            ) TO '{output_path}' (FORMAT PARQUET)
        """)
        logger.debug(f'    {column}.parquet 衍生完成')

    logger.success('复权填充完成')
