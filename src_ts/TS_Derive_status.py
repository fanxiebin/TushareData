""" 衍生层：基于DuckDB原始表生成ST/涨跌停/市值分层状态宽表与状态码表

与提取层同构（SQL计算+PIVOT+COPY直出parquet），替代原PyQI侧TS_Extract_status.py的pandas后处理：
- ST状态：上市日/更名公告日/退市日构成事件流，ASOF JOIN取各交易日最近事件（退市优先于更名），
  收盘价<1元的非退市覆盖为*ST
- 涨跌停：收盘/开盘/最低(高)价与涨跌停价的比较经CASE优先级树判定，LAG判定次日打开
- 市值分层：流通市值逐日横截面分位数（PERCENT_RANK原生窗口），与旧pandas rank/count口径
  仅在贴阈值约±1/n的极窄带内可能有每日1~2只股票的档位差，属已接受的迁移偏差
"""

from pathlib import Path

import duckdb
from tqdm import tqdm

from conf_ts.status_config import (
    ST_CODES, LIMIT_CODES, CAP_CODES, CAP_LABEL_THRESHOLDS, STATUS_CODE_ROWS,
)
from conf_ts.logger_config import get_logger

logger = get_logger(__name__)

# 稠密网格：全部交易日×全部非北交所股票，无daily行的位置补NULL（对应旧pandas宽表的NaN）。
# 辅助表字段以daily行为准（与提取层LEFT JOIN对齐语义一致）
_GRID_SQL = """
CREATE OR REPLACE TEMP VIEW grid AS
SELECT c.trade_date, s.ts_code,
       d.open, d.high, d.low, d.close, d.amount,
       CASE WHEN d.ts_code IS NOT NULL THEN a.adj_factor END AS adj_factor,
       CASE WHEN d.ts_code IS NOT NULL THEN l.up_limit END AS up_limit,
       CASE WHEN d.ts_code IS NOT NULL THEN l.down_limit END AS down_limit,
       CASE WHEN d.ts_code IS NOT NULL THEN b.circ_mv END AS circ_mv,
       CASE WHEN d.ts_code IS NOT NULL THEN b.turnover_rate_f END AS turnover_rate_f
FROM (SELECT DISTINCT trade_date FROM daily) c
CROSS JOIN (SELECT DISTINCT ts_code FROM daily WHERE ts_code NOT LIKE '%.BJ') s
LEFT JOIN daily d ON d.ts_code = s.ts_code AND d.trade_date = c.trade_date
LEFT JOIN adj_factor a ON a.ts_code = s.ts_code AND a.trade_date = c.trade_date
LEFT JOIN stk_limit l ON l.ts_code = s.ts_code AND l.trade_date = c.trade_date
LEFT JOIN daily_basic b ON b.ts_code = s.ts_code AND b.trade_date = c.trade_date
"""

# ST状态：事件流+ASOF取最近事件。优先级与旧pandas逐步覆盖语义一致：退市(最后应用) > 更名 > 上市
_ST_VIEWS_SQL = f"""
CREATE OR REPLACE TEMP VIEW nc_events AS
SELECT ts_code, ann_date,
       CASE WHEN starts_with(n, '退') OR ends_with(n, '退') THEN '{ST_CODES['退市']}'
            WHEN starts_with(n, '*ST') THEN '{ST_CODES['*ST']}'
            WHEN starts_with(n, 'ST') THEN '{ST_CODES['ST']}'
            ELSE '{ST_CODES['正常']}'
       END AS status
FROM (SELECT ts_code, ann_date, trim(name) AS n
      FROM namechange WHERE ts_code NOT LIKE '%.BJ');

CREATE OR REPLACE TEMP VIEW stock_attrs AS
SELECT s.ts_code, sl.list_date, sl.delist_date,
       CASE WHEN sl.ts_code IS NULL THEN f.first_date END AS fallback_start
FROM (SELECT DISTINCT ts_code FROM daily WHERE ts_code NOT LIKE '%.BJ') s
LEFT JOIN (SELECT DISTINCT ON (ts_code) ts_code, list_date, delist_date
           FROM stock_list WHERE ts_code NOT LIKE '%.BJ') sl ON sl.ts_code = s.ts_code
LEFT JOIN (SELECT ts_code, min(trade_date) AS first_date FROM daily
           WHERE ts_code NOT LIKE '%.BJ' GROUP BY ts_code) f ON f.ts_code = s.ts_code;

CREATE OR REPLACE TEMP VIEW st_status AS
SELECT trade_date, ts_code,
       CASE WHEN close IS NOT NULL AND close < 1.0 AND base <> '{ST_CODES['退市']}'
            THEN '{ST_CODES['*ST']}' ELSE base END AS st
FROM (
    SELECT g.trade_date, g.ts_code, g.close,
           CASE
               WHEN a.delist_date IS NOT NULL AND g.trade_date >= a.delist_date THEN '{ST_CODES['退市']}'
               WHEN e.status IS NOT NULL THEN e.status
               WHEN (a.list_date IS NOT NULL AND g.trade_date >= a.list_date)
                 OR (a.list_date IS NULL AND a.fallback_start IS NOT NULL AND g.trade_date >= a.fallback_start)
               THEN '{ST_CODES['正常']}'
               ELSE '{ST_CODES['未上市']}'
           END AS base
    FROM grid g
    JOIN stock_attrs a ON a.ts_code = g.ts_code
    ASOF LEFT JOIN nc_events e ON e.ts_code = g.ts_code AND g.trade_date >= e.ann_date
);
"""

# 涨跌停：布尔标记经CASE优先级树判定。CASE顺序为旧pandas mask应用顺序的逆序（后应用者先匹配），
# LAG对齐旧宽表shift(1, fill_value=False)的全局帧语义（稠密网格保证）
_LIMIT_VIEWS_SQL = f"""
CREATE OR REPLACE TEMP VIEW limit_updown AS
SELECT trade_date, ts_code,
       (close IS NOT NULL) AS has_data,
       COALESCE(up_limit >= 999999.0, FALSE) AS no_limit,
       COALESCE(NOT (up_limit >= 999999.0) AND close >= up_limit, FALSE) AS close_up,
       COALESCE(NOT (up_limit >= 999999.0) AND open >= up_limit, FALSE) AS open_up,
       COALESCE(NOT (up_limit >= 999999.0) AND low >= up_limit, FALSE) AS low_up,
       COALESCE(NOT (up_limit >= 999999.0) AND close <= down_limit, FALSE) AS close_down,
       COALESCE(NOT (up_limit >= 999999.0) AND open <= down_limit, FALSE) AS open_down,
       COALESCE(NOT (up_limit >= 999999.0) AND high <= down_limit, FALSE) AS high_down
FROM grid;

CREATE OR REPLACE TEMP VIEW limit_status AS
SELECT trade_date, ts_code,
       CASE
           WHEN NOT has_data THEN NULL
           WHEN prev_down AND NOT close_down AND NOT close_up THEN '{LIMIT_CODES['down_open_next']}'
           WHEN prev_up AND NOT close_up AND NOT close_down THEN '{LIMIT_CODES['up_open_next']}'
           WHEN close_down AND open_down AND high_down THEN '{LIMIT_CODES['down_level_3']}'
           WHEN close_down AND open_down THEN '{LIMIT_CODES['down_level_2']}'
           WHEN close_down THEN '{LIMIT_CODES['down_level_1']}'
           WHEN close_up AND open_up AND low_up THEN '{LIMIT_CODES['up_level_3']}'
           WHEN close_up AND open_up THEN '{LIMIT_CODES['up_level_2']}'
           WHEN close_up THEN '{LIMIT_CODES['up_level_1']}'
           WHEN no_limit THEN '{LIMIT_CODES['no_limit']}'
           ELSE '{LIMIT_CODES['normal']}'
       END AS lim
FROM (
    SELECT l.*, COALESCE(LAG(close_up) OVER w, FALSE) AS prev_up,
              COALESCE(LAG(close_down) OVER w, FALSE) AS prev_down
    FROM limit_updown l
    WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
);
"""

# 市值分层：PERCENT_RANK原生窗口（分母为n-1，与旧pandas rank/n口径的差异仅在阈值窄带内，
# 每日约1~2只贴边股票降一档，已接受；浮点市值不会并列，平局语义差异无影响）
_CAP_VIEWS_SQL = f"""
CREATE OR REPLACE TEMP VIEW cap_rank AS
SELECT trade_date, ts_code,
       PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY circ_mv) AS pct
FROM grid
WHERE circ_mv IS NOT NULL;

CREATE OR REPLACE TEMP VIEW cap_status AS
SELECT g.trade_date, g.ts_code,
       CASE WHEN r.pct IS NULL THEN NULL
            WHEN r.pct <= {CAP_LABEL_THRESHOLDS['small_quantile']} THEN '{CAP_CODES['small']}'
            WHEN r.pct >= {CAP_LABEL_THRESHOLDS['large_quantile']} THEN '{CAP_CODES['large']}'
            ELSE '{CAP_CODES['mid']}'
       END AS cap
FROM grid g
LEFT JOIN cap_rank r ON r.ts_code = g.ts_code AND r.trade_date = g.trade_date;
"""

# (输出文件名, 视图名, 值列名, 视图DDL)
_STATUS_OUTPUTS = [
    ('ST', 'st_status', 'st', _ST_VIEWS_SQL),
    ('limit', 'limit_status', 'lim', _LIMIT_VIEWS_SQL),
    ('cap', 'cap_status', 'cap', _CAP_VIEWS_SQL),
]


def build_grid(con: duckdb.DuckDBPyConnection) -> None:
    """ 创建稠密网格临时视图（衍生层公共基座，processed衍生同样依赖） """
    con.execute(_GRID_SQL)


def _assert_inputs(con: duckdb.DuckDBPyConnection) -> None:
    """ 输入质量检查（与旧pandas版校验一致：名称无效报错、涨跌停冲突报错） """
    n_bad = con.execute(
        "SELECT count(*) FROM namechange "
        "WHERE ts_code NOT LIKE '%.BJ' AND (name IS NULL OR trim(name) = '')"
    ).fetchone()[0]
    if n_bad:
        raise ValueError(f'namechange存在{n_bad}条name缺失/空记录，请先清洗上游数据')

    n_dup = con.execute(
        'SELECT count(*) - count(DISTINCT ts_code) FROM stock_list'
    ).fetchone()[0]
    if n_dup:
        raise ValueError(f'stock_list存在{n_dup}条重复ts_code记录')


def _sql_literal(v) -> str:
    return 'NULL' if v is None else "'" + str(v).replace("'", "''") + "'"


def derive_status(con: duckdb.DuckDBPyConnection, extr_status_dir: Path) -> None:
    """ 生成ST/涨跌停/市值分层状态宽表和状态码表到extr_status_dir """
    logger.info('衍生状态宽表...')
    extr_status_dir.mkdir(parents=True, exist_ok=True)
    _assert_inputs(con)
    build_grid(con)

    for _, _, _, view_sql in _STATUS_OUTPUTS:
        con.execute(view_sql)

    n_conflict = con.execute(
        'SELECT count(*) FROM limit_updown WHERE close_up AND close_down'
    ).fetchone()[0]
    if n_conflict:
        raise ValueError(f'发现{n_conflict}个涨停跌停冲突数据点，请检查数据清洗过程')

    for name, view, col, _ in tqdm(_STATUS_OUTPUTS, desc='状态衍生进度...'):
        output_path = (extr_status_dir / f'{name}.parquet').as_posix()  # as_posix避免Windows反斜杠被SQL解释为转义符
        con.execute(f"""
            COPY (
                SELECT * FROM (
                    PIVOT (SELECT trade_date, ts_code, {col} FROM {view}) ON ts_code USING first({col})
                ) ORDER BY trade_date
            ) TO '{output_path}' (FORMAT PARQUET)
        """)
        logger.debug(f'    {name}.parquet 衍生完成')

    # 状态码表随数据导出，下游PyQI直接读取，契约跟着数据走
    values = ',\n            '.join(
        f"('{kind}', '{typ}', {_sql_literal(code)}, {_sql_literal(desc)}, {'TRUE' if buyable else 'FALSE'})"
        for kind, typ, code, desc, buyable in STATUS_CODE_ROWS
    )
    codes_path = (extr_status_dir / 'status_codes.parquet').as_posix()
    con.execute(f"""
        COPY (
            SELECT * FROM (VALUES
                {values}
            ) AS t(status_kind, type, code, description, buyable)
        ) TO '{codes_path}' (FORMAT PARQUET)
    """)
    logger.success('状态衍生完成')
