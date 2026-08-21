from pathlib import Path

import pandas as pd

from conf_ts.TS_API_config import DATA_CONFIGS
from conf_ts.dirs_config import dirs, init_dirs
from conf_ts.logger_config import get_logger
from tools.download_status import STATUS_FILE_NAME, register_completed_dates


logger = get_logger(__name__)


def compact_dataset(dataset_dir: Path, dataset_name: str) -> None:
    parquet_files = sorted(dataset_dir.glob('*.parquet'))
    delta_files = [path for path in parquet_files if path.name.startswith('delta_')]
    if not delta_files:
        logger.info(f'{dataset_name} 无增量文件需要合并')
        return

    frames = []
    base_path = dataset_dir / 'base.parquet'
    if base_path.exists():
        frames.append(pd.read_parquet(base_path, engine='pyarrow'))
    frames.extend(pd.read_parquet(path, engine='pyarrow') for path in delta_files)

    merged = pd.concat(frames, ignore_index=True)
    dedup_keys = DATA_CONFIGS[dataset_name]['dedup_keys']
    date_column = DATA_CONFIGS[dataset_name]['date_column']
    merged = merged.drop_duplicates(subset=dedup_keys, keep='last')
    temp_path = dataset_dir / 'base.tmp'
    merged.to_parquet(temp_path, engine='pyarrow', index=False)
    temp_path.replace(base_path)

    logical_dates = sorted(merged[date_column].astype('string').unique().tolist())
    register_completed_dates(dataset_dir / STATUS_FILE_NAME, logical_dates, len(merged))

    for delta_file in delta_files:
        delta_file.unlink()
    logger.success(f'{dataset_name} 合并完成，当前 base 记录数: {len(merged)}')


def compact_all_datasets() -> None:
    init_dirs()
    for root_key in ['raw_data', 'raw_status']:
        root_dir = dirs[root_key]
        for dataset_dir in sorted(root_dir.iterdir()):
            if not dataset_dir.is_dir():
                continue
            dataset_name = dataset_dir.name
            if dataset_name not in DATA_CONFIGS:
                continue
            compact_dataset(dataset_dir, dataset_name)


if __name__ == '__main__':
    compact_all_datasets()