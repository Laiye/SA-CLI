# 更新日志

版本标签与 `pyproject.toml` 的 `version` 保持一致；可能影响既有用法的变化在「行为变化」中单独列出。

## [未发布]

### 新增

- **`ref-level`（参考电平）校准命令**（别名 `reflevel` / `参考电平`）：以 −10 dBm 为参考点，逐点改变频谱仪参考电平并用 Delta 标记核对幅度读数变化
  - 默认点集 −10, 0, 10, −20, −30, −40, −50, −60, −70 dBm（顺序即执行顺序：先参考点、再向上、再向下）
  - 频谱仪：中心 = 校准信号频率（默认 50 MHz）、span 10 kHz、参考电平 −10 dBm、RBW 1 kHz、VBW 30 Hz、1 dB/div；信号源：同频、初始 ≈ −11 dBm
  - 建立参考时微调信号源使峰值读数落在 ±0.5 dB 内，记录实际设置值 **S0**；后续点按 S = S0 + Δ 计算（Δ = Lref − (−10)，不再固定用 −11 dBm）
  - 按规范顺序调整：升高参考电平先设频谱仪再设信号源，降低则先设信号源再设频谱仪（有测试固定该顺序）
  - 安全：`--max-sg-power`（默认 10 dBm）超限即中止，避免频谱仪输入过载；弱信号点可经 `--average-count` + `--average-below` 启用 trace 平均
  - 导出每点 Lref / S / Δ / Δmeas / 误差 / S0，结论为实际 S0 与最大读数偏差
- `validation.validate_levels()`：允许 0 与负值的电平列表校验（`cal_point_defaults()` 现可传入自定义校验器）
- **`freq-reading`（频率读数）校准命令**（别名 `freq` / `频率读数`）：在各校准频率点（默认 1 / 10 / 100 / 1000 / 10000 / 26500 MHz）用频谱仪 marker 峰值读数核对显示频率
  - 每个频率点设三个扫频宽度：1 MHz 点 0.01/0.1/1 MHz；10 MHz 点 0.1/1/10 MHz；≥100 MHz 点 1/10/100 MHz
  - 频谱仪参考电平 0 dBm、信号源 −1 dBm；采样点数 `Points` 默认 1001，显示分辨力 `span/(Points-1)`
  - 读数以**仪器显示为准**：指令读数按显示分辨力量化到显示栅格后作为显示值参与结论，同时导出原始读数（`reading_hz` 与 `raw_error_hz`）
  - 显示文本按仪器样式给出：单位按量级自动切换（可用 `--unit` 强制 Hz/kHz/MHz/GHz），小数位数由显示分辨力决定，同一行的显示值/分辨力/偏差小数位对齐（例：100 MHz 点、Span 10 MHz → 分辨力 0.01 MHz → 显示 `100.00 MHz`）
  - 导出结论：`max_abs_error_hz`（含对应频率/扫频宽度）、`max_abs_relative_ppm`、`max_error_in_resolution_units`
- 频谱仪指令集新增 `set_sweep_points`（`:SWEep:POINts`），并新增 `DEFAULT_SWEEP_POINTS` 等默认值
- 所有命令的「测量结果」改为等宽表格输出（新增 `cli/table.py`：数值列右对齐、中文列宽按 2 列计算），README 各命令示例同步更新

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
