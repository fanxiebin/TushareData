from datetime import datetime
from pathlib import Path

from beartype import beartype
import pandas as pd


STATUS_COLUMNS = [
    'logical_date',
    'status',
    'row_count',
    'updated_at',
    'message',
]

STATUS_FILE_NAME = 'status.csv'


@beartype
def init_status_table(status_file: Path) -> None:
    status_file.parent.mkdir(parents=True, exist_ok=True)
    if status_file.exists():
        return
    pd.DataFrame(columns=STATUS_COLUMNS).to_csv(status_file, index=False)


@beartype
def load_status_table(status_file: Path) -> pd.DataFrame:
    init_status_table(status_file)
    table = pd.read_csv(status_file, dtype='string')
    # 防止手工意外修改导致验证表结构不完整，如果缺少字段则抛出异常提示修复
    missing_columns = [column for column in STATUS_COLUMNS if column not in table.columns]
    if missing_columns:
        raise ValueError(f'下载状态表缺少字段: {missing_columns}')
    return table[STATUS_COLUMNS].fillna('')


@beartype
def save_status_table(status_file: Path, table: pd.DataFrame) -> None:
    table = table[STATUS_COLUMNS].sort_values(['logical_date'], ignore_index=True)
    temp_file = status_file.with_suffix('.tmp')
    table.to_csv(temp_file, index=False)
    temp_file.replace(status_file)


@beartype
def upsert_status_entries(status_file: Path, rows: list[dict[str, str | int]]) -> None:
    if not rows:
        return

    table = load_status_table(status_file)
    updated_at = datetime.now().strftime('%Y%m%d_%H%M%S')
    rows_df = pd.DataFrame([
        {
            'logical_date': row['logical_date'],
            'status': row['status'],
            'row_count': str(row['row_count']),
            'updated_at': updated_at,
            'message': row.get('message', ''),
        }
        for row in rows
    ])
    logical_dates = rows_df['logical_date'].tolist()
    table = table.loc[~table['logical_date'].isin(logical_dates)]
    table = pd.concat([table, rows_df], ignore_index=True)
    save_status_table(status_file, table)


@beartype
def register_completed_dates(
    status_file: Path,
    logical_dates: list[str],
    row_count: int,
) -> None:
    table = load_status_table(status_file)
    if logical_dates:
        date_mask = table['logical_date'].isin(logical_dates)
        table = table.loc[~date_mask]
    rows = [
        {
            'logical_date': date,
            'status': 'success',
            'row_count': str(row_count),
            'updated_at': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'message': '',
        }
        for date in logical_dates
    ]
    if rows:
        table = pd.concat([table, pd.DataFrame(rows)], ignore_index=True)
    save_status_table(status_file, table)


@beartype
def get_completed_dates(status_file: Path) -> set[str]:
    table = load_status_table(status_file)
    dataset_rows = table.loc[table['status'].isin({'success', 'empty'})]
    return set(dataset_rows['logical_date'].tolist())