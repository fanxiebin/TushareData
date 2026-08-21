""" Tushare 数据下载配置常量 """
import tushare as ts

# 下载key
pro = ts.pro_api('***REMOVED***')
pro._DataApi__http_url = "http://***REMOVED***:8010/" # type: ignore

# 下载函数接口
DATA_CONFIGS = {
    'daily': {
        'fields': ["ts_code", "trade_date", "open", "high", "low", "close", "pct_chg", "amount"],
        'download_func': lambda pro, date, fields: pro.daily(trade_date=date, fields=fields),
        'file_name': 'daily.parquet',
        'date_column': 'trade_date',
        'dedup_keys': ['ts_code', 'trade_date'],
        'use_trading_calendar': True,
    },
    'adj_factor': {
        'fields': ["ts_code", "trade_date", "adj_factor"],
        'download_func': lambda pro, date, fields: pro.adj_factor(trade_date=date, fields=fields),
        'file_name': 'adj_factor.parquet',
        'date_column': 'trade_date',
        'dedup_keys': ['ts_code', 'trade_date'],
        'use_trading_calendar': True,
    },
    'daily_basic': {
        'fields': ["ts_code", "trade_date", "turnover_rate", "turnover_rate_f", "volume_ratio", "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_ratio", "dv_ttm", "total_mv", "circ_mv"],
        'download_func': lambda pro, date, fields: pro.daily_basic(trade_date=date, fields=fields),
        'file_name': 'daily_basic.parquet',
        'date_column': 'trade_date',
        'dedup_keys': ['ts_code', 'trade_date'],
        'use_trading_calendar': True,
    },
    'stk_limit': {
        'fields': ["ts_code", "trade_date", "up_limit", "down_limit"],
        'download_func': lambda pro, date, fields: pro.stk_limit(trade_date=date, fields=fields),
        'file_name': 'stk_limit.parquet',
        'date_column': 'trade_date',
        'dedup_keys': ['ts_code', 'trade_date'],
        'use_trading_calendar': True,
    },
    'namechange': {
        'fields': ["ts_code", "name", "start_date", "ann_date", "change_reason"], # namechange不下载end_date，因为只有股票未来下一次更名时才会知道上一次更名的end_date，因此增量下载时end_date值为nan。
        'download_func': lambda pro, date, fields: pro.namechange(start_date=date, end_date=date, fields=fields),
        'file_name': 'namechange.parquet',
        'date_column': 'ann_date',
        'dedup_keys': ['ts_code', 'ann_date'],
        'use_trading_calendar': False,
    },
    '000001.SH': {
        'fields': ["ts_code", "trade_date", "open", "high", "low", "close", "pct_chg", "amount"],
        'download_func': lambda pro, date, fields: pro.index_daily(ts_code='000001.SH', trade_date=date, fields=fields),
        'file_name': '000001.SH.parquet',
        'date_column': 'trade_date',
        'dedup_keys': ['ts_code', 'trade_date'],
        'use_trading_calendar': True,
    },
    '399001.SZ': {
        'fields': ["ts_code", "trade_date", "open", "high", "low", "close", "pct_chg", "amount"],
        'download_func': lambda pro, date, fields: pro.index_daily(ts_code='399001.SZ', trade_date=date, fields=fields),
        'file_name': '399001.SZ.parquet',
        'date_column': 'trade_date',
        'dedup_keys': ['ts_code', 'trade_date'],
        'use_trading_calendar': True,
    },
    '399006.SZ': {
        'fields': ["ts_code", "trade_date", "open", "high", "low", "close", "pct_chg", "amount"],
        'download_func': lambda pro, date, fields: pro.index_daily(ts_code='399006.SZ', trade_date=date, fields=fields),
        'file_name': '399006.SZ.parquet',
        'date_column': 'trade_date',
        'dedup_keys': ['ts_code', 'trade_date'],
        'use_trading_calendar': True,
    },
}
