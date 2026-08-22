import shutil
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, cast
from beartype import beartype
from beartype.vale import Is
from conf_ts.logger_config import get_logger
from conf_ts.TS_API_config import DATA_CONFIGS

# 获取logger
logger = get_logger(__name__)

ExistingDirectory = Annotated[Path, Is[lambda path: path.exists() and path.is_dir()]]
ConfiguredDatasetName = Annotated[str, Is[lambda value: value in DATA_CONFIGS]]

@beartype
def backup_directory(data_dir: ExistingDirectory, backup_dir: Path) -> None:
    """
    备份整个数据目录

    参数:
        data_dir: Path, 数据目录路径
        backup_dir: Path, 备份目录路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dirname = f"data_backup_{timestamp}"
    full_backup_dir = backup_dir / backup_dirname

    try:
        full_backup_dir.mkdir(parents=True, exist_ok=True)

        # 递归复制缓存数据文件与状态文件，保留子目录结构。
        for pattern in ["*.parquet", "*.csv"]:
            for file_path in data_dir.rglob(pattern):
                dest_path = full_backup_dir / file_path.relative_to(data_dir)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest_path)

        logger.success(f"数据目录备份成功: {full_backup_dir}")
    except Exception as e:
        logger.error(f"数据目录备份失败: {str(e)}")

def optimize_dtypes(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """优化DataFrame的数据类型以减少内存占用

    优化策略：
    - float64 -> float32（减少内存到一半）
    - 日期列自动检测并转换为datetime64
    - object -> string，重复率高时进一步转换为分类数组
    """
    # 将双精度数据转换为单精度
    memory_before = int(df.memory_usage(deep=True).sum())
    float64_cols = df.select_dtypes(include=['float64']).columns
    if len(float64_cols) > 0:
        # 使用 numpy 类型而不是字符串，性能略好
        df[float64_cols] = df[float64_cols].astype(np.float32)

    # 如果df的列名称以date开头或结尾且列的格式不为datetime类型，则尝试将该列转换为datetime类型
    date_cols = df.columns[df.columns.str.startswith('date') | df.columns.str.endswith('date')].tolist()
    for col in date_cols:
        if df[col].dtype != 'datetime64[ns]':
            df[col] = pd.to_datetime(df[col])

    # 将object数据转换为字符串，并在重复率较高的情况下进一步转换为分类数组
    object_cols = df.select_dtypes(include=['object']).columns
    for col in object_cols:
        df[col] = df[col].astype('string')
        unique_ratio = df[col].nunique() / len(df) # 计算重复率
        if unique_ratio < 0.3:
            df[col] = df[col].astype('category')
    memory_after = int(df.memory_usage(deep=True).sum())

    return df, memory_before, memory_after


@beartype
def load_dataset_dirs_as_dict(
    root_directory: ExistingDirectory,
    dataset_names: list[ConfiguredDatasetName],
    optimize_memory: bool = True,
) -> dict[str, pd.DataFrame]:
    """按数据集子目录加载所有 parquet，并在目录内拼接。"""
    data_dict = {}
    for dataset_name in dataset_names:
        dataset_dir = root_directory / dataset_name
        if not dataset_dir.exists():
            logger.warning(f"数据集目录不存在: {dataset_dir}")
            continue

        parquet_files = sorted(
            dataset_dir.glob('*.parquet'),
            key=lambda path: (path.name != 'base.parquet', path.name),
        )
        if not parquet_files:
            logger.warning(f"数据集目录内没有 parquet 文件: {dataset_dir}")
            continue
        
        # 核心数据读取函数
        parquet_paths: Any = [str(path) for path in parquet_files]
        df = pd.read_parquet(parquet_paths)
        # 验证数据集中是否存在重复主键数据，如果存在则抛出异常并提供重复数据的样例以便调试。
        dedup_keys = cast(list[str], DATA_CONFIGS[dataset_name]['dedup_keys']) # 显式类型转换以满足类型检查器要求，消除后续静态类型告警。
        duplicate_mask = df.duplicated(subset=dedup_keys, keep=False)
        if duplicate_mask.any():
            duplicate_rows = df.loc[duplicate_mask, dedup_keys].sort_values(dedup_keys)
            duplicate_samples = duplicate_rows.head(10).to_dict('records')
            raise ValueError(
                f"数据集 {dataset_name} 存在重复主键数据: 重复行数={int(duplicate_mask.sum())}, "
                f"重复键样例={duplicate_samples}"
            )

        if optimize_memory:
            df, _, _ = optimize_dtypes(df)
        data_dict[dataset_name] = df
        logger.info(f"加载数据集 {dataset_name}: {len(parquet_files)} 个文件, {len(df)} 条记录")

    return data_dict
