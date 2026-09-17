# 更新日志

版本标签与 `pyproject.toml` 的 `version` 保持一致；可能影响既有用法的变化在「行为变化」中单独列出。

## [未发布]

### 新增

- **`freq-reading`（频率读数）校准命令**（别名 `freq` / `频率读数`）：在各校准频率点（默认 1 / 10 / 100 / 1000 / 10000 / 26500 MHz）用频谱仪 marker 峰值读数核对显示频率
  - 每个频率点设三个扫频宽度：1 MHz 点 0.01/0.1/1 MHz；10 MHz 点 0.1/1/10 MHz；≥100 MHz 点 1/10/100 MHz
  - 频谱仪参考电平 0 dBm、信号源 −1 dBm；采样点数 `Points` 默认 1001，显示分辨力 `span/(Points-1)`
  - 读数以**仪器显示为准**：指令读数按显示分辨力量化到显示栅格后作为显示值参与结论，同时导出原始读数（`reading_hz` 与 `raw_error_hz`）
  - 导出结论：`max_abs_error_hz`（含对应频率/扫频宽度）、`max_abs_relative_ppm`、`max_error_in_resolution_units`
- 频谱仪指令集新增 `set_sweep_points`（`:SWEep:POINts`），并新增 `DEFAULT_SWEEP_POINTS` 等默认值

## [0.2.0] - 2026-09-17

### 变更

**打包结构重构**

- 迁移到 `src/sa_cli/` 包布局，按职责拆分 `cli/`、`instruments/`、`measurements/`、`data/`，新增 `validation.py`、`errors.py`
- 入口点 `sa-cli = sa_cli.cli.main:main`，新增 `python -m sa_cli`；`python main.py` 保留为兼容转发
- SCPI 指令集与 `cal_points.json` 随包分发，通过 `importlib.resources` 读取，不再依赖工作目录

**等待与失败判定**

- 等待改为 `sleep` 依赖注入（按仪器注入、dry-run 不等待），不再修改测量模块的全局等待状态
- `*OPC?` 超时或查询失败 → 中止当前校准点并保留已完成点；单次查询受剩余时间预算限制，结束后恢复原 VISA 超时
- `_find_edge` 达到步数上限未收敛 → 报错；对数/线性刻度峰值调整未收敛 → 报错（dry-run 除外）

**结果导出**

- 同目录临时文件 + 原子替换，导出失败时保留原有文件
- 拒绝非有限值（NaN / Infinity），JSON 使用 `allow_nan=False`
- 导出前校验扩展名与父目录；校验失败时不连接仪器

**配置**

- `cal_points.json` 必须为非空、有限正数且不重复
- 随包 `cal_points.json` 只解析一次；设置 `SA_CLI_DATA_DIR` 时每次实时读取，运行期修改立即生效

**清理**

- 删除 `measurements/common.py` 的 `_opc_done()` 与测试中的 `read_bytes()` 死代码
- `argparse` 显式 `prog="sa-cli"`，`python -m sa_cli --help` 不再显示 `__main__.py`

### 行为变化（可能影响既有用法）

| 变化 | 说明 |
|---|---|
| OPC 等待超时不再容忍 | 单个校准点等待超过 `OPC_TIMEOUT_S`（默认 60 s）将失败并返回退出码 1；必要时调大该常量 |
| 不收敛即失败 | 扫描边沿 / 峰值调整不收敛时报错，不再输出可疑数据 |
| CSV 增加元数据列 | 每行包含 `command`、`partial` 及该命令的 `export_meta` 与结论字段（如 `carrier_hz`、`max_abs_delta_db`） |
| `cal_points.json` 严格校验 | 出现重复点或非正数将直接报错 |
| `SA_CLI_DATA_DIR` 不再回退 | 覆盖目录缺少指令集 JSON 时抛 `FileNotFoundError`；仅 `cal_points.json` 缺失仍回退代码默认值 |

## [0.1.0] - 2026-09-11

首个版本：7 个校准命令（`phase-noise` / `rbw` / `bw60` / `rbw-switch` / `sweep-width` / `log-scale` / `linear-scale`，含中文别名）、`*OPC?` 同步等待、RF 关断兜底、部分结果导出、逐点进度与 ETA、`--dry-run`、数值参数的 `k/M/G` 后缀、`sa-cli` 入口点。

> 该标签对应**重构前**的顶层模块布局（仓库根为 `main.py`、`instruments.py`、`measurements.py` 等），提交 `7cc21e9`；`0.2.0` 起为 `src/sa_cli/` 包布局。
