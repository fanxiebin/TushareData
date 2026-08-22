# TushareData
从Tushare下载A股股票数据，存储于DuckDB数据库（`data/tushare.duckdb`），并透视导出宽表Parquet（`data/1_extracted_data/`）。

## 安装
```bash
pip install -e .
```

## 运行
```bash
python update_main.py
```
流程：备份数据库文件 → 增量下载（数据与下载状态同事务写入） → SQL透视导出宽表。

下游读取建议以只读方式连接：`duckdb.connect('data/tushare.duckdb', read_only=True)`（DuckDB单文件单写者）。

项目将 `ipykernel` 固定为 `6.31.0`，避免环境重建或重新安装时被解析到更新版本。
