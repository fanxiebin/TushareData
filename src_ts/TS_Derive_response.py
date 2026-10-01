""" 衍生层：未来收益响应，供统计研究作测量标签

前复权收盘价上计算 t → t+h 简单收益率，长期出口价用目标日的中心移动平均：
    RR_h = CMA_w(close)_{t+h} / close_t - 1
窗口：3日 w=1（即日收盘），10日 w=3，30日 w=9。
中心均价只作用于未来卖出价；买入日收盘是已知事实，保持点值。
实际退市日及之后价格记 0；退市整理期保留真实价格。
持有期内实际退市则收益强制为 -1，不受中心均价或停牌缺价影响；买入日已退市或价格缺失则为 NULL。
"""

from pathlib import Path

import pandas as pd
from beartype import beartype

from conf_ts.logger_config import get_logger
from conf_ts.status_config import ST_CODES

logger = get_logger(__name__)

# (持有交易日 h, 出口中心均价窗口 w)，w 为奇数；w=1 即点值收盘价
RESPONSE_SPECS = (
    (3, 1),
    (10, 3),
    (30, 9),
)
DELIST_CODE = ST_CODES['退市']


def _read_wide(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path, engine='pyarrow')
    return df.set_index('trade_date')


@beartype
def derive_response(processed_dir: Path, status_dir: Path, response_dir: Path) -> None:
    logger.info('衍生未来收益响应（中心均价出口）...')
    close_path = processed_dir / 'close.parquet'
    st_path = status_dir / 'ST.parquet'
    if not close_path.exists():
        raise FileNotFoundError(f'缺少前复权收盘价: {close_path}')
    if not st_path.exists():
        raise FileNotFoundError(f'缺少 ST 状态宽表: {st_path}')
    response_dir.mkdir(parents=True, exist_ok=True)

    close = _read_wide(close_path)
    st = _read_wide(st_path)
    if not close.index.equals(st.index) or not close.columns.equals(st.columns):
        raise ValueError('close 与 ST 网格不一致')
    delisted = st == DELIST_CODE
    close = close.mask(delisted, 0)

    for horizon, window in RESPONSE_SPECS:
        if window < 1 or window % 2 == 0:
            raise ValueError(f'中心均价窗口必须为正奇数，收到 h={horizon} w={window}')
        future = close.rolling(window=window, center=True).mean().shift(-horizon)
        # 实际退市状态持续有效；目标日已退市意味着持有期内发生了退市。
        rr = (future / close - 1).mask(delisted.shift(-horizon, fill_value=False), -1)
        rr = rr.where(close > 0).astype('float32')
        rr.reset_index().to_parquet(response_dir / f'RR_{horizon}.parquet', engine='pyarrow', index=False)
        logger.info(f'RR_{horizon}.parquet 完成（w={window}）')

    logger.success('未来收益响应衍生完成')
