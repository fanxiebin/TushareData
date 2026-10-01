""" 衍生层：个股趋势特征

前复权收盘价上、截至 t 日收盘（含当日）的后向趋势，单位都是窗口简单收益率。
close 中的缺失和非正价格不参与。

1 日、3 日为两端实际变化：close_t / close_{t-h} - 1，两端都须有价格。
10 / 30 / 90 日为 log 价格对交易日序号的 OLS 拟合总收益 exp(b*(w-1))-1。
窗口内有效价格不少于 80%，且当日有价格；缺失日留在时间轴上，不把后续点前移。
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd
from beartype import beartype

from conf_ts.logger_config import get_logger

logger = get_logger(__name__)

# (周期, 'point' 实际变化 | 'ols' 对数价格拟合)
TREND_SPECS = (
    (1, 'point'),
    (3, 'point'),
    (10, 'ols'),
    (30, 'ols'),
    (90, 'ols'),
)
MIN_VALID_FRAC = 0.8


def _read_wide(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path, engine='pyarrow')
    return df.set_index('trade_date')


def rolling_ols_span(logp: np.ndarray, window: int) -> np.ndarray:
    """窗口内有限 log 价格对交易日序号的 OLS 拟合总收益 exp(b*(w-1))-1。

    logp 形状 (交易日, 股票)，无效为 NaN。缺失点不参与拟合，也不前移后续点。
    不足两点或斜率非有限则为 NaN。当日是否成交、窗口内有效点是否够，由调用方筛选。
    """
    if window < 2:
        raise ValueError(f'OLS 窗口至少 2 日，收到 {window}')
    t_n, n_n = logp.shape
    out = np.full((t_n, n_n), np.nan, dtype=np.float64)
    x = np.arange(window, dtype=np.float64)[:, None]
    span = window - 1
    for t in range(window - 1, t_n):
        block = logp[t - window + 1:t + 1]
        valid = np.isfinite(block)
        cnt = valid.sum(axis=0)
        y = np.where(valid, block, 0.0)
        x_sum = (x * valid).sum(axis=0)
        y_sum = y.sum(axis=0)
        x_mean = np.divide(x_sum, cnt, out=np.zeros(n_n), where=cnt > 0)
        y_mean = np.divide(y_sum, cnt, out=np.zeros(n_n), where=cnt > 0)
        xc = np.where(valid, x - x_mean, 0.0)
        yc = np.where(valid, y - y_mean, 0.0)
        sxx = np.einsum('ij,ij->j', xc, xc)
        sxy = np.einsum('ij,ij->j', xc, yc)
        ok = sxx > 0
        b = np.divide(sxy, sxx, out=np.zeros(n_n), where=ok)
        span_ret = np.expm1(b * span)
        out[t] = np.where(ok & np.isfinite(span_ret), span_ret, np.nan)
    return out


def _write(df: pd.DataFrame, path: Path) -> None:
    df.index.name = 'trade_date'
    df.astype('float32').reset_index().to_parquet(path, engine='pyarrow', index=False)


@beartype
def derive_features(processed_dir: Path, features_dir: Path) -> None:
    logger.info('衍生趋势特征（1/3 日变化，10/30/90 日 OLS）...')
    close_path = processed_dir / 'close.parquet'
    if not close_path.exists():
        raise FileNotFoundError(f'缺少前复权收盘价: {close_path}')
    features_dir.mkdir(parents=True, exist_ok=True)

    close = _read_wide(close_path)
    px = close.where(close > 0)
    logp = np.log(px.to_numpy(dtype=np.float64)) # 为保证增长拟合的线性，需要对股价取对数

    for horizon, kind in TREND_SPECS:
        if kind == 'point':
            tr = px / px.shift(horizon) - 1
        elif kind == 'ols':
            tr = pd.DataFrame(
                rolling_ols_span(logp, horizon),
                index=px.index,
                columns=px.columns,
            )
            min_valid = math.ceil(MIN_VALID_FRAC * horizon)
            enough = px.notna().rolling(horizon, min_periods=1).sum() >= min_valid
            tr = tr.where(px.notna() & enough)
        else:
            raise ValueError(f'未知趋势类型 {kind}')
        _write(tr, features_dir / f'TR_{horizon}.parquet')
        logger.info(f'    TR_{horizon}.parquet 完成（{kind}）')

    logger.success('趋势特征衍生完成')
