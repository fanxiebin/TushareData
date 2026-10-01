""" 日频离散涨跌幅与分市场指数

个股：ROUND(pct_chg) 后 |x|>20 并入 ±20，TINYINT。网格与 close 对齐，停牌为 NULL。
市场：主板 000001.SH，创业/科创 399006.SZ，连续 pct_chg 另存。
"""

from pathlib import Path

import duckdb
from beartype import beartype

from conf_ts.logger_config import get_logger
from src_ts.TS_Derive_status import build_grid

logger = get_logger(__name__)

CLIP = 20
MARKET_INDEXES = ('000001.SH', '399006.SZ')
_ROC = (
    f"CASE WHEN pct_chg IS NULL THEN NULL ELSE CAST("
    f"LEAST({CLIP}, GREATEST(-{CLIP}, ROUND(pct_chg))) AS TINYINT) END"
)
_BOARD = """CASE
    WHEN ts_code LIKE '30%.SZ' THEN '创业板'
    WHEN ts_code LIKE '688%.SH' OR ts_code LIKE '689%.SH' THEN '科创板'
    ELSE '主板' END"""
_MKT = """CASE
    WHEN ts_code LIKE '30%.SZ' OR ts_code LIKE '688%.SH' OR ts_code LIKE '689%.SH'
    THEN '399006.SZ' ELSE '000001.SH' END"""


@beartype
def derive_market(con: duckdb.DuckDBPyConnection, features_dir: Path) -> None:
    logger.info('衍生日频离散涨跌幅与市场指数...')
    market_dir = features_dir / 'market'
    market_dir.mkdir(parents=True, exist_ok=True)
    build_grid(con)

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW roc_1d AS
        SELECT trade_date, ts_code, {_ROC} AS roc_1_disc FROM grid
    """)
    lo, hi = con.execute("SELECT min(roc_1_disc), max(roc_1_disc) FROM roc_1d").fetchone()
    if lo < -CLIP or hi > CLIP:
        raise ValueError(f'roc_1_disc 超出 ±{CLIP}: min={lo} max={hi}')

    stock_path = (features_dir / 'close_ROC_1_disc.parquet').as_posix()
    con.execute(f"""
        COPY (
            SELECT * FROM (
                PIVOT (SELECT trade_date, ts_code, roc_1_disc FROM roc_1d)
                ON ts_code USING first(roc_1_disc)
            ) ORDER BY trade_date
        ) TO '{stock_path}' (FORMAT PARQUET)
    """)
    n_null, n_all = con.execute(
        "SELECT count(*) FILTER (WHERE roc_1_disc IS NULL), count(*) FROM roc_1d"
    ).fetchone()
    logger.info(f'    close_ROC_1_disc.parquet 完成，NULL {n_null}/{n_all}')

    board_path = (market_dir / 'board.parquet').as_posix()
    con.execute(f"""
        COPY (
            SELECT ts_code, {_BOARD} AS board, {_MKT} AS mkt_index
            FROM (SELECT DISTINCT ts_code FROM daily WHERE ts_code NOT LIKE '%.BJ')
            ORDER BY ts_code
        ) TO '{board_path}' (FORMAT PARQUET)
    """)

    n_cal = con.execute("SELECT count(DISTINCT trade_date) FROM daily").fetchone()[0]
    for idx in MARKET_INDEXES:
        n_idx = con.execute(
            "SELECT count(*) FROM index_daily WHERE ts_code = ?", [idx]
        ).fetchone()[0]
        if n_idx != n_cal:
            raise ValueError(f'{idx} 日数 {n_idx} 与 daily 交易日 {n_cal} 不一致')
        idx_path = (market_dir / f'{idx}.parquet').as_posix()
        con.execute(f"""
            COPY (
                SELECT trade_date, pct_chg, {_ROC} AS roc_1_disc
                FROM index_daily WHERE ts_code = '{idx}'
                ORDER BY trade_date
            ) TO '{idx_path}' (FORMAT PARQUET)
        """)

    logger.success('离散涨跌幅与市场指数衍生完成')
