# SA-CLI

基于 JSON 指令集的频谱分析仪 & 信号发生器 CLI 控制与测量工具。通过 PyVISA 与仪器通信，支持任意 VISA 传输层（GPIB、USB、TCP/IP）。

## 环境要求

- Python 3.8+
- PyVISA + 对应后端（如 `pyvisa-py` 或 NI-VISA）
- 已安装 VISA 驱动并正确识别仪器

### 推荐：用虚拟环境隔离系统 Python（避免依赖版本冲突）

不同项目对 PyVISA / pytest 等库的版本要求往往不同，直接装在系统 Python 里会互相覆盖。用 `venv` 为项目建独立环境，依赖全部落在项目目录的 `.venv/` 内：

```bash
# 1. 创建虚拟环境（Python 3.3+ 内置，无需额外安装）
python -m venv .venv

# 2. 激活（激活后 pip / python / sa-cli 都指向 .venv）
#    Windows PowerShell
.\.venv\Scripts\Activate.ps1
#    Windows CMD
.venv\Scripts\activate.bat
#    Linux / macOS
source .venv/bin/activate

# 3. 安装项目本体 + 运行时依赖（editable 模式：改代码即时生效，无需重装）
pip install -e .

# 4. 可选：安装测试依赖
pip install -e ".[dev]"

# 5. 验证
sa-cli --help
```

不想激活时，直接用虚拟环境里的解释器执行也可以：

```bash
# Windows
.venv\Scripts\python -m main rbw --rbw-list 100 1000
# Linux / macOS
.venv/bin/python -m main rbw --rbw-list 100 1000
```

> 例：系统 Python 装的是 PyVISA 1.15，项目在 `.venv` 里装 1.16，两者互不干扰；`.venv/` 已加入 `.gitignore`，不会污染仓库。退出环境用 `deactivate`。

**Windows 常见问题**

| 现象 | 处理 |
|---|---|
| PowerShell 报“禁止运行脚本 / cannot be loaded because running scripts is disabled” | 执行一次 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，或改用 `.venv\Scripts\activate.bat`（CMD），也可不激活，直接用 `.venv\Scripts\python` / `.venv\Scripts\sa-cli.exe` |
| `python -m venv .venv` 报 ensurepip 失败 | 用 `python -m venv --without-pip .venv` 创建，再执行 `.venv\Scripts\python -m ensurepip --upgrade` 补装 pip |
| 激活后 `python` 仍指向系统解释器 | 确认提示符前出现 `(.venv)`，或用 `Get-Command python` 检查路径；VS Code/终端需重开 |

### 不使用虚拟环境（不推荐）

```bash
pip install -r requirements.txt          # 运行依赖
pip install -r requirements-dev.txt      # 含测试依赖
```

## 支持仪器

### 频谱分析仪

| 系列 | 型号 |
|---|---|
| Agilent PSA | E4440A, E4443A, E4445A, E4446A, E4448A |

### 信号发生器

| 系列 | 型号 |
|---|---|
| Keysight/Agilent | N5183B, E8257D, E4438C |

## 项目结构

```
SA-CLI/
  main.py                  # CLI 入口（参数解析、命令注册与统一分发、结果导出/部分结果导出）
  instruments.py           # 仪器封装（Instrument 基类 + 具体仪器 + VISA 会话管理）
  measurements.py          # 测量算法（相位噪声 / RBW / -60dB 带宽 / 扫频宽度 / 对数·线性刻度）与 *OPC? 同步等待
  config.py                # 默认配置（仪器地址、JSON 数据目录，支持环境变量覆盖）
  report.py                # 测量结果导出（.json / .csv）
  spectrum_analyzer.json   # 频谱分析仪 SCPI 指令集定义（含 init_sweep 单次扫描触发）
  signal_generator.json    # 信号发生器 SCPI 指令集定义
  cal_points.json          # 各命令默认校准点
  pyproject.toml           # 项目元数据、依赖、sa-cli 入口点与 pytest 配置
  MANIFEST.in              # sdist 打包清单（含 JSON 指令集）
  requirements.txt         # 运行依赖（与 pyproject 保持一致，兼容非 PEP 517 场景）
  requirements-dev.txt     # 测试依赖（pytest）
  .gitignore               # 忽略 .venv/ 与 Python 缓存等
  tests/                   # 单元测试（模拟 VISA，无需真实仪器）
```

## 配置

仪器地址可通过环境变量覆盖（CLI 参数优先级更高）：

```bash
export SA_CLI_SG_ADDR=TCPIP::192.168.1.10::INSTR
export SA_CLI_SA_ADDR=TCPIP::192.168.1.20::INSTR
```

JSON 指令集与校准点的查找目录（`SA_CLI_DATA_DIR`）默认按以下顺序自动确定，一般无需设置：

1. 环境变量 `SA_CLI_DATA_DIR`
2. 模块所在目录（`pip install -e .` 即仓库根目录）
3. 当前工作目录

非 editable 安装（`pip install .`）时 JSON 不在 site-packages 中，此时把 `SA_CLI_DATA_DIR` 指向存放 JSON 的目录即可：

```bash
export SA_CLI_DATA_DIR=/path/to/SA-CLI
```

### 默认校准点（cal_points.json）

各校准项目的默认校准点定义在 `cal_points.json`，未传命令行参数时使用；命令行参数优先级更高。默认内容：

| 项目 | 默认校准点 (Hz) |
|---|---|
| phase-noise | 100, 1000, 10k, 100k |
| rbw | 100, 1000, 3000, 10k, 30k, 100k, 300k, 1M |
| bw60 | 100, 1000, 3000, 10k, 30k, 100k, 300k, 1M |
| sweep-width | 100, 1000, 10k, 100k, 1M, 10M, 100M, 1G |
| log-scale-1db | 1, 2, 3, 4, 5, 6, 7, 8, 9 (dB) |
| log-scale-10db | 10, 20, 30, 40, 50, 60, 70, 80 (dB) |
| linear-scale | 4, 8, 12, 16, 20 (dB) |

```json
{
  "phase-noise": [100, 1000, 10E3, 100E3],
  "rbw": [100, 1000, 3000, 10E3, 30E3, 100E3, 300E3, 1E6],
  "bw60": [100, 1000, 3000, 10E3, 30E3, 100E3, 300E3, 1E6],
  "sweep-width": [100, 1000, 10E3, 100E3, 1E6, 10E6, 100E6, 1E9],
  "log-scale-1db": [1, 2, 3, 4, 5, 6, 7, 8, 9],
  "log-scale-10db": [10, 20, 30, 40, 50, 60, 70, 80],
  "linear-scale": [4, 8, 12, 16, 20]
}
```

## 结果导出

每个命令均支持 `--output <file>`，按扩展名导出为 CSV 或 JSON：

```bash
python main.py rbw --output result.csv
python main.py phase-noise -o 100 --output result.json
```

**部分结果导出**：多校准点测量（如 8 个 RBW 点）中途某点失败时，若指定了 `--output`，已完成点的结果会自动写入文件，导出对象带 `"partial": true` 标记，命令退出码为 1；未指定 `--output` 则仅记录错误、不落盘。

```json
{ "command": "rbw", "partial": true, "results": [ {"rbw_hz": 100, "measured_hz": 100.3, ...} ] }
```

## 测试

使用模拟 VISA 的单元测试，无需真实仪器（在虚拟环境内运行，见「环境要求」）：

```bash
pip install -e ".[dev]"     # 或 pip install -r requirements-dev.txt
python -m pytest
```

## 快速开始

安装（`pip install -e .`）后会生成 `sa-cli` 命令，与 `python main.py` 完全等价；下文的 `python main.py` 均可替换为 `sa-cli`。

```bash
# 查看所有命令
sa-cli --help                      # 或 python main.py --help

# 查看子命令帮助
sa-cli phase-noise --help
sa-cli rbw --help
sa-cli bw60 --help
sa-cli sweep-width --help

# dry-run：不连接仪器，打印将发送的完整 SCPI 命令序列（调试指令集/验收流程用）
sa-cli rbw --rbw-list 100 1000 --dry-run
```

## 命令

> 多校准点命令运行时会逐点打印进度与预计剩余时间（按已完成点的平均用时估算），例如：
> `[3/8] 测量 RBW=100.0 Hz（已用 1分20秒 · 预计剩余 4分10秒）`，前两个点完成前只显示序号与名称。

### 1. 噪声边带 — `phase-noise` / `pn` / `噪声边带`

单边带相位噪声测量 (dBc/Hz)。采用零扫宽方法：先将频偏点移至 Center，Span=0，设置 VBW=10Hz 降噪后单次读取。± 频偏两侧各测一次，取噪声更差的一侧作为 ΔL。

```bash
# 基本用法 - 1 GHz 载波，100 Hz 频偏
python main.py phase-noise --offset 100

# 多个频偏校准点
python main.py phase-noise -o 100 1000 10E3 100E3

# 简写 / 中文别名
python main.py pn -o 100
python main.py 噪声边带 --offset 100
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--offset` | `-o` | float[] | cal_points.json | 频偏列表 (Hz)，可传多个，默认 `100 1000 10k 100k` |
| `--carrier` | `-c` | float | 1e9 | 载波频率 (Hz) |
| `--ref-level` | `-r` | float | 0 | 参考电平 (dBm) |
| `--atten` | `-a` | float | 10 | 输入衰减 (dB) |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**完整示例：**

```bash
python main.py pn \
  --offset 10e3 \
  --carrier 2.4e9 \
  --ref-level -10 \
  --atten 20 \
  --sg-addr TCPIP::192.168.1.10::INSTR \
  --sa-addr TCPIP::192.168.1.20::INSTR
```

**输出示例：**

```
===== 噪声边带测量 =====
  载波频率: 1000000000 Hz
  频偏:      100 Hz
  测量模式:  零扫宽 (Span=0)
  RBW:       10.0 Hz
  参考电平:  0 dBm
  衰减:      10 dB

  载波功率: 0.12 dBm
  正侧 100 Hz 偏移: Δ=-85.21 dB
  负侧 100 Hz 偏移: Δ=-87.10 dB
  选用正侧 ΔL = -85.21 dB
相位噪声 @ 100 Hz 偏移 (Span=0, RBW=10.0 Hz): -95.21 dBc/Hz

===== 测量结果 =====
  测量模式:  零扫宽 (Span=0)
  RBW:      10.0 Hz
  相位噪声 @ 100 Hz 偏移: -95.21 dBc/Hz
```

---

### 2. 分辨力带宽 — `rbw` / `分辨力带宽`

RBW 3dB 准确性验证。采用差分法：信号源先降 3dB 建立 delta 参考，恢复功率后调频率使 SA 滤波器衰减 3dB（delta→0），找到 -3dB 频率边沿，两侧频率差即为实测 RBW。

```bash
# 默认 50 MHz 载波，测 [100, 1000, 10000] Hz
python main.py rbw

# 中文别名
python main.py 分辨力带宽 -c 100e6 -b 300 1000 3000 10000
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--carrier` | `-c` | float | 50e6 | 载波频率 (Hz) |
| `--rbw-list` | `-b` | float[] | [100, 1000, 10000] | 待测 RBW 列表 |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**测量配置：**

| 项 | 值 |
|---|---|
| 频谱仪设置 | Ref Level -20 dBm，Span 3×RBW，垂直刻度 1 dB/div |
| 检测器 | Sample |
| 差分参考 | SG 降至 -24 dBm 建 peak，恢复 -21 dBm（+3dB） |
| 粗搜步长 | `RBW / 20`，阈值 `delta ≤ 0.1 dB` |
| 精调步长 | `RBW / 200`，收敛阈值 `\|delta\| ≤ 0.05 dB` |

**输出示例：**

```
===== 分辨力带宽 (RBW) 准确性验证 =====
  载波频率: 50000000 Hz
  RBW 列表: [100.0, 1000.0, 10000.0]

--- 测量 RBW = 100 Hz ---
  粗搜 左侧: 49999953.0 Hz (delta=0.095, 10 步)
  精调 左侧收敛: 49999952.5 Hz (delta=0.032)
  粗搜 右侧: 50000052.0 Hz (delta=0.088, 11 步)
  精调 右侧收敛: 50000052.8 Hz (delta=0.041)
  设定 100 Hz，实测 3dB 带宽 = 100.3 Hz (误差 +0.3%)

===== 验证结果 =====
  设定 100 Hz → 实测 100.3 Hz (误差 +0.3%)
  设定 1000 Hz → 实测 998.5 Hz (误差 -0.1%)
  设定 10000 Hz → 实测 10012.0 Hz (误差 +0.1%)
```

---

### 3. -60 dB 带宽 — `bw60` / `带宽60`

-60 dB 带宽测量。方法与 RBW 类似：信号源降 60dB 建立参考，恢复后调频率找 -60dB 边沿。通过 VBW 分档降噪，Detector 为 Sample。

```bash
# 默认 50 MHz 载波，测 [100, 1000, 10000] Hz
python main.py bw60

# 中文别名
python main.py 带宽60 -c 50e6 -b 300 1000 3000
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--carrier` | `-c` | float | 50e6 | 载波频率 (Hz) |
| `--rbw-list` | `-b` | float[] | [100, 1000, 10000] | 待测 RBW 列表 |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**测量配置：**

| 项 | 值 |
|---|---|
| 频谱仪设置 | Ref Level 0 dBm，Span 20×RBW，垂直刻度 10 dB/div |
| 检测器 | Sample |
| VBW 降噪 | RBW≤100 → 10 Hz；100<RBW≤10k → 100 Hz；RBW>10k → 1 kHz |
| 差分参考 | SG 降至 -61 dBm 建 peak，恢复 -1 dBm（+60dB） |
| 粗搜步长 | `RBW / 20 × 1.5`，阈值 `delta ≤ 1.0 dB` |
| 精调步长 | `RBW / 100`，收敛阈值 `\|delta\| ≤ 0.5 dB` |
| 调频稳定 | 每步调频后 `*OPC?` 等待扫描完成（保底 1s） |

**输出示例：**

```
===== -60 dB 带宽测量 =====
  载波频率: 50000000 Hz
  RBW 列表: [100.0, 1000.0, 10000.0]

--- 测量 -60 dB 带宽 (RBW=100 Hz) ---
  粗搜 左侧: 49999500.0 Hz (delta=0.080, 28 步)
  精调 左侧收敛: 49999498.5 Hz (delta=0.035)
  粗搜 右侧: 50000502.0 Hz (delta=0.092, 26 步)
  精调 右侧收敛: 50000503.2 Hz (delta=0.041)
  -60 dB 带宽 = 1004.7 Hz (设定 RBW=100 Hz)

===== 测量结果 =====
  设定 RBW=100 Hz → -60 dB 带宽: 1004.7 Hz
  设定 RBW=1000 Hz → -60 dB 带宽: 10120.3 Hz
  设定 RBW=10000 Hz → -60 dB 带宽: 110500.0 Hz
```

---

### 4. 扫频宽度 — `sweep-width` / `sw` / `扫频宽度`

扫频宽度准确性验证。设置两个已知频点，用频谱仪 marker 读取显示频率并求差值，与理论差值 0.8×span 比较。

**两种模式（按 span 自动选择）：**

| 条件 | 中心频率 | 信号源频点 |
|---|---|---|
| span ≤ 1 GHz | 1 GHz | 1 GHz ± 0.4×span |
| span > 1 GHz | span/2 | 0.1×span 与 0.9×span |

**计算公式：**

- 相对误差 `δ = (频率差 - 0.8×span) / (0.8×span)`
- 被校扫频宽度 `= 频率差 / 0.8`

**小 span 预处理（按 span 比例逐级对中）：**

当 span 小于 `--align-threshold`（默认 100 kHz）时，频谱仪与信号源晶振频率准确度不一致会导致标称相同频率不落在频谱仪中心，且频谱仪对中精度受显示分辨率（窗口/点数）限制——对 10 Hz 这类小 span，固定窗口无法保证峰值落在屏内。此时按 span 的 `1000× → 100× → 10×` 逐级缩小窗口做 peak_search + `set_marker_to_center`（起窗取 `max(1000×span, --align-span)` 以保证捕获晶振偏差），最后在测量 span 下用测量 RBW（`span/20`）再对中一次，使对中精度与待测 span 相称。>1 GHz 模式中心频率为 span/2，偏差与 span 成比例，天然无此问题，不做对中。

**注意**：span ≤ 100 Hz 时窄 RBW 导致波形更新很慢，程序会自动将稳定等待下限延长至约 4 s（其余 span 为 2 s），配合 `*OPC?` 等待扫描真正完成后再搜索峰值，避免读到陈旧数据。

```bash
# 基本用法 - 测 1 GHz 扫频宽度
python main.py sweep-width --span 1e9

# 多个校准点 - 一次性测量多个扫频宽度
python main.py sweep-width -s 0.1e9 1e9 1.6e9

# 小 span（如 10 Hz）会自动逐级对中；可调整捕获窗口，或设阈值 0 关闭
python main.py sweep-width -s 10 100 --align-span 1e6 --align-threshold 100k
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--span` | `-s` | float[] | **必填** | 待测扫频宽度列表 (Hz)，可传多个，如 `0.1e9 1e9 1.6e9` |
| `--ref-level` | `-r` | float | 0 | 参考电平 (dBm) |
| `--sg-power` | | float | -1 | 信号源电平 (dBm) |
| `--align-threshold` | | float | 100k | 峰值对中预处理阈值 (Hz)，span 小于该值启用 |
| `--align-span` | | float | 1e6 | 对中初始捕获窗口下限 (Hz)，起窗取 `max(1000×span, 该值)` |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**输出示例：**

```
===== 扫频宽度准确性验证 =====
  待测扫频宽度: 1600000000 Hz
  参考电平:     0 dBm
  信号源电平:   -1 dBm
  测量模式:     span > 1 GHz（中心 span/2，频点 0.1*span 与 0.9*span）

  频点1: 160000000 Hz → 显示 159999900.00 Hz
  频点2: 1440000000 Hz → 显示 1439999800.00 Hz
  频率差: 1280000000.00 Hz（理论 0.8×span = 1280000000.00 Hz）
  相对误差 δ: -0.01 %
  被校扫频宽度: 1600000000.00 Hz

===== 测量结果 =====
  频率差:        1280000000.00 Hz
  相对误差 δ:    -0.01 %
  被校扫频宽度:  1600000000.00 Hz
```

---

### 5. 对数刻度 — `log-scale` / `log` / `对数刻度`

对数刻度（垂直刻度）准确性验证。先调整信号源电平使频谱仪峰值为 0 ± 0.2 dB，打开 marker delta 后按固定步进衰减信号源，记录各衰减点的 marker delta 读数。

**两种模式（`--scale` 选择）：**

| 模式 | 垂直刻度 | 衰减步进 | 默认校准点 (dB) |
|---|---|---|---|
| `--scale 1` | 1 dB/div | 1 dB | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| `--scale 10` | 10 dB/div | 10 dB | 10, 20, 30, 40, 50, 60, 70, 80 |

**测量配置：** 中心频率 50 MHz（可改）、参考电平 0 dBm、span 10 kHz、RBW 1 kHz、VBW 30 Hz、输入衰减 10 dB。峰值调整目标 0 dB，容差 ±0.2 dB。

```bash
# 1 dB/div 模式（默认校准点 1~9 dB）
python main.py log-scale

# 10 dB/div 模式（默认校准点 10~80 dB）
python main.py log --scale 10

# 自定义校准点 / 中文别名 / 导出
python main.py log-scale --scale 1 -p 1 3 5 --output result.csv
python main.py 对数刻度 --scale 10 -c 100e6
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--scale` | | int | 1 | 垂直刻度模式：1（1 dB/div）或 10（10 dB/div） |
| `--carrier` | `-c` | float | 50e6 | 中心频率 (Hz) |
| `--points` | `-p` | float[] | cal_points.json | 校准点列表 (dB)，默认按模式读取 |
| `--ref-level` | `-r` | float | 0 | 参考电平 (dBm) |
| `--atten` | `-a` | float | 10 | 输入衰减 (dB) |
| `--span` | | float | 10k | 扫频宽度 (Hz) |
| `--rbw` | | float | 1k | 分辨力带宽 (Hz) |
| `--vbw` | | float | 30 | 视频带宽 (Hz) |
| `--sg-power` | | float | -1 | 信号源电平 (dBm) |
| `--settle` | | float | 2 | 每步衰减后的稳定等待下限 (s)，`*OPC?` 保证扫描完成（SA 侧保底不超过 0.5s） |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**输出示例：**

```
===== 对数刻度准确性验证 =====
  垂直刻度:   1 dB/div
  中心频率:   50000000 Hz
  ...
  峰值调整至 0.01 dBm（SG 电平 0.01 dBm）

===== 测量结果 =====
  衰减 1 dB → marker delta -1.02 dB（偏差 -0.02 dB）
  衰减 2 dB → marker delta -1.99 dB（偏差 +0.01 dB）
  ...
```

---

### 6. 线性刻度 — `linear-scale` / `lin` / `线性刻度`

线性刻度（电压）准确性验证。0 dBm 在 50Ω 下对应 223.6 mV。先调整信号源电平使频谱仪线性显示峰值为 223.6 mV ± 0.2 mV，再按校准点逐级衰减信号源，测量对应峰值电平 Vm，与理论值比较。

**计算公式：** `Vn = 1000 × sqrt(0.05 × 10^(-A/10))`（mV），A 为衰减量（dB）；相对误差 `= (Vm - Vn) / 223.6 × 100%`

**测量配置：** 中心频率 50 MHz（可改）、参考电平 0 dBm、span 10 kHz、RBW 3 kHz、垂直刻度为线性模式（`SPACing LIN`）、输入衰减 10 dB。默认校准点 4, 8, 12, 16, 20 dB。

```bash
# 默认校准点 4~20 dB
python main.py linear-scale

# 自定义校准点 / 中文别名 / 导出
python main.py linear-scale -p 4 12 20 --output result.csv
python main.py lin -c 100e6
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--carrier` | `-c` | float | 50e6 | 中心频率 (Hz) |
| `--points` | `-p` | float[] | cal_points.json | 校准点列表 (dB)，默认 4 8 12 16 20 |
| `--ref-level` | `-r` | float | 0 | 参考电平 (dBm) |
| `--atten` | `-a` | float | 10 | 输入衰减 (dB) |
| `--span` | | float | 10k | 扫频宽度 (Hz) |
| `--rbw` | | float | 3k | 分辨力带宽 (Hz) |
| `--sg-power` | | float | -1 | 信号源电平 (dBm) |
| `--target` | | float | 223.6 | 线性峰值目标 (mV) |
| `--tolerance` | | float | 0.2 | 峰值容差 (mV) |
| `--mv-factor` | | float | 1000 | marker 读数换算为 mV 的系数（线性返回 V 用 1000，返回 mV 用 1） |
| `--settle` | | float | 2 | 每步衰减后的稳定等待下限 (s)，`*OPC?` 保证扫描完成（SA 侧保底不超过 0.5s） |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**输出示例：**

```
===== 线性刻度准确性验证 =====
  峰值调整至 223.60 mV（SG 电平 0.00 dBm）

===== 测量结果 =====
  衰减 4 dB → Vm 141.09 mV / 理论 141.09 mV（相对误差 +0.000%）
  衰减 8 dB → Vm 88.94 mV / 理论 88.94 mV（相对误差 +0.000%）
  衰减 20 dB → Vm 22.36 mV / 理论 22.36 mV（相对误差 +0.000%）
```

## 架构说明

### 仪器基类 `Instrument`（`instruments.py`）

从 JSON 文件加载 SCPI 指令集，通过闭包工厂 `_create_methods()` 动态生成实例方法。新增仪器指令只需编辑 JSON，无需改 Python 代码。

```python
class SpectrumAnalyzer(Instrument):
    def __init__(self, resource_address, rm=None):
        super().__init__(resource_address, "spectrum_analyzer.json", rm)
        self.instr.timeout = 60000  # 频谱仪超时 60s（与 OPC 等待上限一致）
```

信号发生器超时放宽至 15s（`instruments.py`），以覆盖频率/电平稳定等待；`visa_session` 上下文管理器在退出时（无论正常或异常）会强制发送 `rf_off`，确保测量结束后 RF 输出关闭。

### 公共搜索函数 `_find_edge`（`measurements.py`）

两阶段逼近滤波边沿（`cal_rbw` 和 `cal_bw60` 共用）：

- **Phase 1 粗搜** — 大步向外走，直到 delta ≤ 1.0 dB（粗搜阈值）
- **Phase 2 精调** — delta > 0 继续向外，delta < 0 回退，小步逼近，|delta| ≤ 0.5 dB 收敛

参数（`cal_rbw` / `cal_bw60` 差异）：

| 参数 | 3dB (rbw) | 60dB (bw60) |
|---|---|---|
| 粗搜步长 | `RBW / 20` | `RBW / 20 × 1.5` |
| 精调步长 | `RBW / 200` | `RBW / 100` |
| 粗搜阈值 | delta ≤ 0.1 dB | delta ≤ 1.0 dB |
| 精调阈值 | \|delta\| ≤ 0.05 dB | \|delta\| ≤ 0.5 dB |
| 调频稳定 | 每步 `*OPC?` 等扫描完成（保底 0.1s） | 每步 `*OPC?` 等扫描完成（保底 1s，VBW 收窄扫频慢） |

两侧测量之间 SG 会先回到载波频率并等待稳定，避免残留 trace 数据干扰另一侧搜索。

### 等待与同步机制（`*OPC?`）

所有"等待仪器就绪"均基于 IEEE 488.2 标准通用命令 `*OPC?`（跨厂商兼容，PSA 系列与 N5183B/E8257D/E4438C 均支持），由 `measurements.py` 中三个帮助函数实现：

- **`_wait_opc(instr, min_sleep, timeout_s)`** — 先保底等待 `min_sleep`（覆盖 preset 内部校准等 `*OPC?` 未跟踪的操作），再轮询 `*OPC?` 返回 1；超时仅告警不抛异常，按原路径降级继续。
- **`_wait_sweep(spec_an, min_sleep, timeout_s)`** — 等待频谱仪完成一次扫描：切单次扫描（`:INITiate:CONTinuous OFF`）→ 触发（`:INITiate:IMMediate`，即 `init_sweep` action）→ `*OPC?` → 恢复连续扫描。**连续扫描模式下 `*OPC?` 语义不可靠（可能立即返回或永久阻塞），必须搭配单次扫描模式使用**。
- **`_opc_done(instr)`** — `*OPC?` 返回 1 的判定，I/O 异常或非数值返回安全降级为未完成。

等待策略：**批量下发连续配置后一次性等待**（如 `cal_rbw` 每点的 7 条频谱仪配置合并为一次 `_wait_sweep`），取代原来的逐条固定 sleep；`*OPC?` 保证扫描真正完成后再读 marker，既提速又避免"固定等待短于实际扫描时间导致读到过期数据"。超时上限与 VISA 超时一致（频谱仪 60s、信号源 15s）。

### 添加新仪器指令

编辑对应的 JSON 文件，格式：

```json
{
  "actions": {
    "action_name": {
      "commands": [":SCPI:COMMAND "],
      "args_num": 1,
      "is_query": false
    }
  }
}
```

| 字段 | 说明 |
|---|---|
| `commands` | SCPI 命令列表（带参数则末尾留空格） |
| `args_num` | 参数个数，0 表示无参 |
| `is_query` | `true` 则调用 `query()`，否则 `write()` |
| `returns` | 仅查询动作：`"float"`（默认，解析失败即报错）或 `"str"`（如 `*IDN?`） |

## 许可证

MIT
