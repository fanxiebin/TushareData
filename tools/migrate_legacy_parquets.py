from pathlib import Path
from datetime import datetime

import pandas as pd

from conf_ts.TS_API_config import DATA_CONFIGS
from conf_ts.dirs_config import dirs, init_dirs
from conf_ts.logger_config import get_logger
from tools.download_status import STATUS_FILE_NAME, init_status_table, normalize_status_table, register_completed_dates, upsert_status_entry


logger = get_logger(__name__)


def migrate_dataset(root_dir: Path, dataset_name: str, source_file: Path) -> None:
    dataset_dir = root_dir / dataset_name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    target_file = dataset_dir / 'base.parquet'
    status_file = dataset_dir / STATUS_FILE_NAME
    if not target_file.exists():
        source_file.replace(target_file)
    df = pd.read_parquet(target_file, engine='pyarrow')
    date_column = DATA_CONFIGS[dataset_name]['date_column']
    logical_dates = sorted(df[date_column].astype('string').unique().tolist())
    init_status_table(status_file)
    register_completed_dates(status_file, logical_dates, len(df))
    logger.success(f'{dataset_name} 迁移完成: {target_file}')


def migrate_stock_list(source_file: Path) -> None:
    stock_list_dir = dirs['raw_status'] / 'stock_list'
    stock_list_dir.mkdir(parents=True, exist_ok=True)
    target_file = stock_list_dir / 'current.parquet'
    if not target_file.exists():
        source_file.replace(target_file)
    status_file = stock_list_dir / STATUS_FILE_NAME
    init_status_table(status_file)
    logical_date = datetime.fromtimestamp(target_file.stat().st_mtime).strftime('%Y%m%d')
    row_count = len(pd.read_parquet(target_file, engine='pyarrow'))
    upsert_status_entry(status_file, logical_date, 'success', row_count)
    logger.success(f'stock_list 迁移完成: {target_file}')


def normalize_existing_status_tables() -> None:
    for root_dir in [dirs['raw_data'], dirs['raw_status']]:
        for status_file in root_dir.rglob(STATUS_FILE_NAME):
            normalize_status_table(status_file)
            logger.success(f'状态文件已规范: {status_file}')


def migrate_legacy_parquets() -> None:
    init_dirs()

    for dataset_name in DATA_CONFIGS:
        source_root = dirs['raw_status'] if dataset_name == 'namechange' else dirs['raw_data']
        source_file = source_root / DATA_CONFIGS[dataset_name]['file_name']
        target_dir = source_root / dataset_name
        if not source_file.exists() and not (target_dir / 'base.parquet').exists():
            continue
        migrate_dataset(source_root, dataset_name, source_file)

    stock_list_source = dirs['raw_status'] / 'stock_list.parquet'
    stock_list_current = dirs['raw_status'] / 'stock_list' / 'current.parquet'
    if stock_list_source.exists() or stock_list_current.exists():
        migrate_stock_list(stock_list_source)

    normalize_existing_status_tables()


if __name__ == '__main__':
    migrate_legacy_parquets()