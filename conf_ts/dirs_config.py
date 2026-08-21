""" TushareData 目录配置文件 """

from pathlib import Path

dir_root = Path('C:/Users/neilf/Documents/GitHub/TushareData')

dirs = {
    'root': dir_root,
    'data': dir_root / 'data',
    'raw_data': dir_root / 'data/0_raw_data',
    'raw_status': dir_root / 'data/0_raw_status',
    'extr_data': dir_root / 'data/1_extracted_data',
    'backup': dir_root / 'data/SS',
}


def init_dirs() -> dict[str, Path]:
    """获取目录配置并确保目录存在。"""
    for _, dir_path in dirs.items():
        dir_path.mkdir(parents=True, exist_ok=True)
    return dirs
