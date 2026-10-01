"""退市整理/实际退市状态与未来收益的回归验证。"""

import tempfile
import unittest
from pathlib import Path

import duckdb
import pandas as pd

from conf_ts.status_config import ST_CODES
from src_ts.db import TABLE_DDL
from src_ts.TS_Derive_response import RESPONSE_SPECS, derive_response
from src_ts.TS_Derive_status import derive_status


class DelistingPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix='tushare_delisting_')
        cls.addClassCleanup(cls.temp_dir.cleanup)
        root = Path(cls.temp_dir.name)
        status_dir = root / 'status'
        processed_dir = root / 'processed'
        response_dir = root / 'response'
        processed_dir.mkdir()
        cls.dates = pd.bdate_range('2020-01-01', periods=80).date

        con = duckdb.connect(':memory:')
        try:
            for ddl in TABLE_DDL:
                con.execute(ddl)

            # 股票代码、上市日位置、退市日位置（None 为尚未退市）。
            stocks = [
                ('000001.SZ', 0, None),
                ('000002.SZ', 2, 50),
                ('000003.SZ', 0, 50),
                ('000004.SZ', 0, None),
                ('000005.SZ', 0, 79),
            ]
            daily_rows = []
            for code, listed, delisted in stocks:
                con.execute(
                    'INSERT INTO stock_list (ts_code, list_date, delist_date) VALUES (?, ?, ?)',
                    [code, cls.dates[listed],
                     cls.dates[delisted] if delisted is not None else None],
                )
                for i in range(listed, delisted if delisted is not None else len(cls.dates)):
                    if code == '000003.SZ' and i >= 48:
                        continue  # 正式退市前停牌两日。
                    close = 0.5 + 0.005 * i if code in ('000002.SZ', '000004.SZ') else 10.0 + i
                    daily_rows.append((code, cls.dates[i], close))
            con.executemany('INSERT INTO daily (ts_code, trade_date, close) VALUES (?, ?, ?)', daily_rows)
            con.executemany(
                'INSERT INTO namechange (ts_code, name, ann_date) VALUES (?, ?, ?)',
                [
                    ('000002.SZ', '*ST测试', cls.dates[5]),
                    ('000002.SZ', '测试退', cls.dates[8]),
                    ('000002.SZ', '普通名称', cls.dates[51]),
                    ('000003.SZ', '退测试', cls.dates[8]),
                    ('000004.SZ', '退测试', cls.dates[8]),
                ],
            )
            derive_status(con, status_dir)
            close_path = (processed_dir / 'close.parquet').as_posix()
            con.execute(f"""
                COPY (
                    SELECT * FROM (
                        PIVOT (SELECT trade_date, ts_code, close FROM grid)
                        ON ts_code USING first(close)
                    ) ORDER BY trade_date
                ) TO '{close_path}' (FORMAT PARQUET)
            """)
        finally:
            con.close()

        derive_response(processed_dir, status_dir, response_dir)
        cls.status = pd.read_parquet(status_dir / 'ST.parquet').set_index('trade_date')
        cls.codes = pd.read_parquet(status_dir / 'status_codes.parquet')
        cls.responses = {
            horizon: pd.read_parquet(response_dir / f'RR_{horizon}.parquet').set_index('trade_date')
            for horizon, _ in RESPONSE_SPECS
        }

    def test_status_distinguishes_announcement_and_actual_delisting(self):
        self.assertEqual(self.status.loc[self.dates[0], '000002.SZ'], ST_CODES['未上市'])
        self.assertEqual(self.status.loc[self.dates[6], '000002.SZ'], ST_CODES['*ST'])
        for code in ('000002.SZ', '000003.SZ', '000004.SZ'):
            with self.subTest(code=code):
                self.assertEqual(self.status.loc[self.dates[8], code], ST_CODES['退市整理'])
        for i in (50, 51, 79):
            with self.subTest(day=i):
                self.assertEqual(self.status.loc[self.dates[i], '000002.SZ'], ST_CODES['退市'])
        self.assertEqual(self.status.loc[self.dates[79], '000004.SZ'], ST_CODES['退市整理'])

    def test_low_price_does_not_override_delisting_period(self):
        self.assertEqual(self.status.loc[self.dates[7], '000002.SZ'], ST_CODES['*ST'])
        self.assertEqual(self.status.loc[self.dates[39], '000002.SZ'], ST_CODES['退市整理'])

    def test_exported_codes_distinguish_both_unbuyable_states(self):
        rows = self.codes[self.codes['status_kind'] == 'ST'].set_index('type')
        for name in ('退市整理', '退市'):
            with self.subTest(name=name):
                self.assertEqual(rows.loc[name, 'code'], ST_CODES[name])
                self.assertFalse(rows.loc[name, 'buyable'])
        self.assertNotEqual(ST_CODES['退市整理'], ST_CODES['退市'])

    def test_delisting_period_keeps_real_returns(self):
        for horizon, _ in RESPONSE_SPECS:
            with self.subTest(horizon=horizon):
                expected = (0.5 + 0.005 * (8 + horizon)) / (0.5 + 0.005 * 8) - 1
                self.assertAlmostEqual(self.responses[horizon].loc[self.dates[8], '000002.SZ'], expected, delta=1e-6)
                self.assertAlmostEqual(self.responses[horizon].loc[self.dates[8], '000004.SZ'], expected, delta=1e-6)

    def test_actual_delisting_is_total_loss_despite_smoothing_or_suspension(self):
        for horizon, _ in RESPONSE_SPECS:
            for code in ('000002.SZ', '000003.SZ'):
                with self.subTest(horizon=horizon, code=code):
                    self.assertEqual(self.responses[horizon].loc[self.dates[50 - horizon], code], -1)

    def test_known_delisting_at_sample_end_is_total_loss(self):
        for horizon, _ in RESPONSE_SPECS:
            with self.subTest(horizon=horizon):
                self.assertEqual(self.responses[horizon].loc[self.dates[79 - horizon], '000005.SZ'], -1)

    def test_invalid_buy_day_or_missing_target_stays_null(self):
        for horizon, _ in RESPONSE_SPECS:
            for day, code in ((0, '000002.SZ'), (49, '000003.SZ'), (50, '000002.SZ'), (79, '000001.SZ')):
                with self.subTest(horizon=horizon, day=day, code=code):
                    self.assertTrue(pd.isna(self.responses[horizon].loc[self.dates[day], code]))

    def test_ordinary_stock_returns_are_unchanged(self):
        for horizon, _ in RESPONSE_SPECS:
            with self.subTest(horizon=horizon):
                expected = (10 + 8 + horizon) / (10 + 8) - 1
                self.assertAlmostEqual(self.responses[horizon].loc[self.dates[8], '000001.SZ'], expected)


if __name__ == '__main__':
    unittest.main()
