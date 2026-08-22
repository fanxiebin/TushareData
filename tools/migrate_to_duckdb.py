""" 一次性迁移脚本：将 parquet 原始数据与 CSV 状态表导入 DuckDB，并输出逐表校验结果。验证通过后删除本脚本。"""
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from conf_ts.dirs_config import dirs
from conf_ts.logger_config import get_logger
from tools.db import connect

logger = get_logger(__name__)

DB_PATH = dirs['data'] / 'tushare.duckdb'
LEGACY_DIR = dirs['data'] / '_legacy'

# 数据集目录名 -> (目标表, 去重键, 日期列, 所属原始根目录)
DATASETS = {
    'daily':       ('daily',       ['ts_code', 'trade_date'], ['trade_date'], '0_raw_data'),
    'adj_factor':  ('adj_factor',  ['ts_code', 'trade_date'], ['trade_date'], '0_raw_data'),
    'daily_basic': ('daily_basic', ['ts_code', 'trade_date'], ['trade_date'], '0_raw_data'),
    'stk_limit':   ('stk_limit',   ['ts_code', 'trade_date'], ['trade_date'], '0_raw_data'),
    '000001.SH':   ('index_daily', ['ts_code', 'trade_date'], ['trade_date'], '0_raw_data'),
    '399001.SZ':   ('index_daily', ['ts_code', 'trade_date'], ['trade_date'], '0_raw_data'),
    '399006.SZ':   ('index_daily', ['ts_code', 'trade_date'], ['trade_date'], '0_raw_data'),
    'namechange':  ('namechange',  ['ts_code', 'ann_date'],   ['start_date', 'ann_date'], '0_raw_status'),
}
DATE_COLUMNS_STOCK_LIST = ['list_date', 'delist_date']


def read_dataset_parquet(dataset_dir: Path) -> pd.DataFrame:
    """ 按base优先、delta按文件名的顺序读取并拼接数据集全部parquet """
    parquet_files = sorted(
        dataset_dir.glob('*.parquet'),
        key=lambda path: (path.name != 'base.parquet', path.name),
    )
    if not parquet_files:
        raise FileNotFoundError(f'数据集目录内没有 parquet 文件: {dataset_dir}')
    return pd.read_parquet([str(path) for path in parquet_files])


def to_db_frame(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    """ 日期列从 'YYYYMMDD' 字符串转为 date 对象（空值保持NaT，入库为NULL） """
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], format='%Y%m%d').dt.date
    return df


def import_dataset(con, dataset_name: str, table: str, dedup_keys: list[str], date_cols: list[str]) -> int:
    """ 导入单个数据集：显式去重后插入目标表，并逐项校验 """
    df = read_dataset_parquet(dirs['data'] / DATASETS[dataset_name][3] / dataset_name)
    rows_raw = len(df)
    df = df.drop_duplicates(subset=dedup_keys, keep='last').reset_index(drop=True)
    rows_dedup = len(df)
    df = to_db_frame(df, date_cols)

    null_keys = int(df[dedup_keys].isna().any(axis=1).sum())
    if null_keys:
        raise ValueError(f'数据集 {dataset_name} 主键列存在 {null_keys} 个空值，无法入库')

    # 多个数据集可能写入同一目标表（如三只指数共用index_daily），因此按插入前后行数差校验
    count_before, = con.execute(f'SELECT count(*) FROM {table}').fetchone()
    con.register('migrating_df', df)
    columns = ', '.join(df.columns)
    con.execute(f'INSERT INTO {table} ({columns}) SELECT {columns} FROM migrating_df')
    count_after, = con.execute(f'SELECT count(*) FROM {table}').fetchone()
    rows_inserted = count_after - count_before

    date_col = 'trade_date' if 'trade_date' in df.columns else date_cols[-1]
    min_db, max_db = con.execute(f'SELECT min({date_col}), max({date_col}) FROM {table}').fetchone()
    logger.success(
        f'{dataset_name} -> {table}: 原始{rows_raw}行, 去重后{rows_dedup}行, '
        f'入库{rows_inserted}行, {date_col}范围[{min_db}, {max_db}]'
    )
    if rows_inserted != rows_dedup:
        raise ValueError(f'{dataset_name} 入库行数 {rows_inserted} 与去重后行数 {rows_dedup} 不一致')


def import_stock_list(con) -> None:
    """ stock_list 为全量快照，直接整表导入（列已是datetime类型） """
    df = pd.read_parquet(dirs['data'] / '0_raw_status' / 'stock_list' / 'current.parquet')
    for col in DATE_COLUMNS_STOCK_LIST:
        df[col] = df[col].dt.date
    con.register('migrating_df', df)
    con.execute('DELETE FROM stock_list')
    con.execute(f'INSERT INTO stock_list ({", ".join(df.columns)}) SELECT {", ".join(df.columns)} FROM migrating_df')
    count_db, = con.execute('SELECT count(*) FROM stock_list').fetchone()
    logger.success(f'stock_list: 入库{count_db}行')
    if count_db != len(df):
        raise ValueError(f'stock_list 入库行数 {count_db} 与源行数 {len(df)} 不一致')


def import_status_tables(con) -> None:
    """ 将各数据集目录的 status.csv 原样导入 download_status（dataset=目录名） """
    total = 0
    for dataset_name in list(DATASETS) + ['stock_list']:
        status_file = dirs['data'] / DATASETS.get(dataset_name, ('', '', '', '0_raw_status'))[3] / dataset_name / 'status.csv'
        if not status_file.exists():
            logger.warning(f'状态文件不存在，跳过: {status_file}')
            continue
        table = pd.read_csv(status_file, dtype='string').fillna('')
        rows = [
            (
                dataset_name,
                row.logical_date,
                row.status,
                int(row.row_count) if row.row_count else 0,
                row.message,
                datetime.strptime(row.updated_at, '%Y%m%d_%H%M%S') if row.updated_at else None,
            )
            for row in table.itertuples()
        ]
        con.executemany('INSERT OR REPLACE INTO download_status VALUES (?, ?, ?, ?, ?, ?)', rows)
        total += len(rows)
        logger.success(f'{dataset_name} 状态导入: {len(rows)}条')
    logger.success(f'download_status 合计导入: {total}条')


def archive_stale_database() -> None:
    """ 将旧版遗留的 tushare.duckdb（内容已过期）归档到 _legacy 目录，避免与新库混淆 """
    if DB_PATH.exists():
        LEGACY_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(DB_PATH), LEGACY_DIR / 'tushare_stale.duckdb')
        logger.warning(f'检测到旧版数据库文件，已归档到: {LEGACY_DIR / "tushare_stale.duckdb"}')


def main() -> None:
    archive_stale_database()
    con = connect(DB_PATH)
    try:
        for dataset_name, (table, dedup_keys, date_cols, _) in DATASETS.items():
            import_dataset(con, dataset_name, table, dedup_keys, date_cols)
        import_stock_list(con)
        import_status_tables(con)
        logger.success('迁移完成，全部校验通过')
    finally:
        con.close()


if __name__ == '__main__':
    main()
