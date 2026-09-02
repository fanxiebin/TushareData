""" DuckDB 连接、库表结构、备份与下载状态查询 """
import shutil
from datetime import datetime
from pathlib import Path

import duckdb
from beartype import beartype
from conf_ts.logger_config import get_logger

logger = get_logger(__name__)

# 库表结构：主键在写入时强制去重（fail fast）；数值列用FLOAT与原float32行为对齐；日期列存DATE
TABLE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS daily (
        ts_code VARCHAR NOT NULL,
        trade_date DATE NOT NULL,
        open FLOAT, high FLOAT, low FLOAT, close FLOAT, pct_chg FLOAT, amount FLOAT,
        PRIMARY KEY (ts_code, trade_date)
    )""",
    """
    CREATE TABLE IF NOT EXISTS adj_factor (
        ts_code VARCHAR NOT NULL,
        trade_date DATE NOT NULL,
        adj_factor FLOAT,
        PRIMARY KEY (ts_code, trade_date)
    )""",
    """
    CREATE TABLE IF NOT EXISTS daily_basic (
        ts_code VARCHAR NOT NULL,
        trade_date DATE NOT NULL,
        turnover_rate FLOAT, turnover_rate_f FLOAT, volume_ratio FLOAT,
        pe FLOAT, pe_ttm FLOAT, pb FLOAT, ps FLOAT, ps_ttm FLOAT,
        dv_ratio FLOAT, dv_ttm FLOAT, total_mv FLOAT, circ_mv FLOAT,
        PRIMARY KEY (ts_code, trade_date)
    )""",
    """
    CREATE TABLE IF NOT EXISTS stk_limit (
        ts_code VARCHAR NOT NULL,
        trade_date DATE NOT NULL,
        up_limit FLOAT, down_limit FLOAT,
        PRIMARY KEY (ts_code, trade_date)
    )""",
    """
    CREATE TABLE IF NOT EXISTS index_daily (
        ts_code VARCHAR NOT NULL,
        trade_date DATE NOT NULL,
        open FLOAT, high FLOAT, low FLOAT, close FLOAT, pct_chg FLOAT, amount FLOAT,
        PRIMARY KEY (ts_code, trade_date)
    )""",
    """
    CREATE TABLE IF NOT EXISTS namechange (
        ts_code VARCHAR NOT NULL,
        name VARCHAR,
        start_date DATE,
        ann_date DATE NOT NULL,
        change_reason VARCHAR,
        PRIMARY KEY (ts_code, ann_date)
    )""",
    """
    CREATE TABLE IF NOT EXISTS stock_list (
        ts_code VARCHAR,
        name VARCHAR,
        industry VARCHAR,
        list_status VARCHAR,
        list_date DATE,
        delist_date DATE
    )""",
    """
    CREATE TABLE IF NOT EXISTS download_status (
        dataset VARCHAR NOT NULL,
        logical_date VARCHAR NOT NULL,
        status VARCHAR,
        row_count INTEGER,
        message VARCHAR,
        updated_at TIMESTAMP,
        PRIMARY KEY (dataset, logical_date)
    )""",
]


@beartype
def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    """ 连接数据库文件并确保库表结构存在 """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    for ddl in TABLE_DDL:
        con.execute(ddl)
    return con


@beartype
def backup_database(db_path: Path, backup_dir: Path) -> None:
    """ 备份数据库文件到带时间戳的备份文件。需在连接建立前调用，避免Windows文件占用 """
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = backup_dir / f'{db_path.stem}_{timestamp}.duckdb'
    shutil.copy2(db_path, backup_file)
    logger.success(f'数据库备份成功: {backup_file}')


@beartype
def get_completed_dates(con: duckdb.DuckDBPyConnection, dataset: str) -> set[str]:
    """ 读取指定数据集已完成（success或empty）的逻辑日期集合 """
    rows = con.execute(
        "SELECT logical_date FROM download_status WHERE dataset = ? AND status IN ('success', 'empty')",
        [dataset],
    ).fetchall()
    return {row[0] for row in rows}
