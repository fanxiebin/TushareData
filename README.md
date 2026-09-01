# TushareData

从 [Tushare](https://tushare.pro) 增量下载A股日线数据，存入 DuckDB 单文件数据库，并用纯 SQL 衍生出股票状态宽表与前复权价格宽表（Parquet），供下游量化研究直接读取。

## 功能特点

- **增量更新**：按交易日逐日下载，数据与下载状态同事务写入 DuckDB，中断重跑不会产生半日数据或重复下载
- **纯 SQL 衍生层**：ST/涨跌停/市值分层状态、前复权、停牌填充全部在 DuckDB 内用 SQL 完成，无 pandas 中间步骤
- **下游零处理**：直接读 Parquet 宽表（行=交易日，列=股票代码），pandas / DuckDB / Polars 均可一行读入

## 环境要求

- Python >= 3.10（在 3.13 上开发验证）
- [Tushare](https://tushare.pro) 账号的 API token（部分接口对账号积分等级有要求，详见 Tushare 官网文档）

## 安装

```bash
pip install -e .
```

## 配置 token

1. 在 [tushare.pro](https://tushare.pro) 注册，于个人主页复制你的 token
2. 在 `conf_ts/` 下新建文件 `token.local`，内容为一行纯文本 token

`token.local` 已被 .gitignore 忽略，不会进入版本库；缺失时程序会报错并提示上述创建方法。

## 运行

在仓库根目录执行：

```bash
python update_main.py
```

流程：备份 DuckDB 文件 → 增量下载原始数据（日线行情、复权因子、每日指标、涨跌停价、三只指数日线、股票更名记录、最新股票清单）→ SQL 衍生导出。日志同时输出到控制台和 `logs/app.log`（保留 30 天）。

下载的日期范围、数据集清单等参数见 `conf_ts/download_config.py`。

Windows 下如需双击运行，可自行在仓库根目录创建 `.bat` 启动脚本（`cd /d <仓库路径>` 后执行上述命令）。

## 输出数据

| 位置 | 内容 |
|---|---|
| `data/tushare.duckdb` | 原始数据库：各下载表 + 下载状态表 |
| `data/1_extracted_status/` | 状态宽表：`ST.parquet`（未上市/正常/ST/*ST/退市）、`limit.parquet`（涨跌停分级）、`cap.parquet`（市值分层）、`status_codes.parquet`（状态码表，附交易视角的可买入标注） |
| `data/2_processed/` | 前复权宽表：`close.parquet`（前复权收盘价）及 `amount` / `circ_mv` / `turnover_rate_f`，停牌期数值向前填充 |
| `data/SS/` | 每次运行前自动备份的数据库文件 |

下游程序需要同时读取 DuckDB 时，请使用只读连接：`duckdb.connect('data/tushare.duckdb', read_only=True)`（DuckDB 单文件同一时刻只允许一个写者）。

## 说明

- 项目将 `ipykernel` 固定为 `6.31.0`，避免环境重建或重新安装时被解析到更新版本。
