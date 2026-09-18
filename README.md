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

```text
SA-CLI/
  src/sa_cli/
    __main__.py              # python -m sa_cli 入口
    cli/
      main.py                # 日志、退出码与命令入口
      parser.py              # 参数声明、数值解析
      commands.py            # 命令注册、调用与结果转换
      table.py               # 控制台结果表格渲染（中文列宽对齐）
    instruments/
      base.py                # JSON 动作加载与 SCPI 通信
      devices.py             # 信号源与频谱仪类型
      session.py             # VISA 生命周期与 RF 关闭
    measurements/
      bandwidth.py           # RBW / -60 dB 带宽与边沿搜索
      rbw_switch.py          # 分辨力带宽转换影响
      freq_reading.py        # 频率读数（marker 显示值为准）
      ref_level.py           # 参考电平（-10 dBm 参考点）
      input_atten.py         # 输入衰减器转换影响（10 dB 参考点）
      phase_noise.py         # 相位噪声
      sweep_width.py         # 扫频宽度与峰值对中
      scale.py               # 对数 / 线性刻度
      common.py              # 同步等待、逐点执行、进度
    data/                    # 随包分发的两个 SCPI JSON 和 cal_points.json
    config.py                # 配置与资源加载
    validation.py            # 数值及校准点校验
    errors.py                # 测量异常与部分结果
    report.py                # JSON / CSV 原子导出
  tests/
    fakes.py                 # 可复用模拟 VISA 资源
    conftest.py              # pytest fixtures
    unit/                    # 配置、仪器与算法测试
    integration/             # CLI、可靠性与包入口测试
  main.py                    # 旧入口兼容转发
  pyproject.toml             # src 包发现、入口点、依赖与包数据
  MANIFEST.in                # 源码发行包清单
  CHANGELOG.md               # 版本变更记录与行为变化清单
```

安装后可用 `sa-cli`、`python -m sa_cli`；仓库内仍支持 `python main.py` 和
`python -m main`。开发时先执行 `python -m pip install -e ".[dev]"`，测试直接导入
已安装的 `sa_cli` 包，不再修改 Python 搜索路径。Python 调用方请将旧的顶层导入
改为 `from sa_cli.instruments import visa_session` 等包导入。


## 配置

仪器地址可通过环境变量覆盖（CLI 参数优先级更高）：

```bash
export SA_CLI_SG_ADDR=TCPIP::192.168.1.10::INSTR
export SA_CLI_SA_ADDR=TCPIP::192.168.1.20::INSTR
```

JSON 指令集与校准点默认通过 `importlib.resources` 从 `sa_cli.data` 读取，
editable 安装和普通 wheel 安装均自带三个 JSON 文件，不依赖当前工作目录。

自定义配置时，把需要使用的两个指令集 JSON 和 `cal_points.json` 放入独立目录，
再设置环境变量（优先于包内资源）：

```powershell
$env:SA_CLI_DATA_DIR = "C:\instrument-config"
```

未提供 `cal_points.json` 时使用代码默认点集；指令集缺失会明确报错，不静默回退。
校准点每次加载都会重新读取配置，支持同一进程切换目录或更新文件。

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
| rbw-switch | 100, 300, 1k, 3k, 10k, 30k, 100k, 300k, 1M |
| freq-reading | 1M, 10M, 100M, 1000M, 10000M, 26500M (Hz) |
| ref-level | −10, 0, 10, −20, −30, −40, −50, −60, −70 (dBm，−10 为参考点) |
| input-atten | 10, 20, 30, 40, 50, 60, 70 (dB，10 为参考点) |

```json
{
  "phase-noise": [100, 1000, 10E3, 100E3],
  "rbw": [100, 1000, 3000, 10E3, 30E3, 100E3, 300E3, 1E6],
  "bw60": [100, 1000, 3000, 10E3, 30E3, 100E3, 300E3, 1E6],
  "sweep-width": [100, 1000, 10E3, 100E3, 1E6, 10E6, 100E6, 1E9],
  "log-scale-1db": [1, 2, 3, 4, 5, 6, 7, 8, 9],
  "log-scale-10db": [10, 20, 30, 40, 50, 60, 70, 80],
  "linear-scale": [4, 8, 12, 16, 20],
  "rbw-switch": [100, 300, 1E3, 3E3, 10E3, 30E3, 100E3, 300E3, 1E6],
  "freq-reading": [1E6, 10E6, 100E6, 1000E6, 10000E6, 26500E6],
  "ref-level": [-10, 0, 10, -20, -30, -40, -50, -60, -70],
  "input-atten": [10, 20, 30, 40, 50, 60, 70]
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

**CSV 列**：每一行 = 该点数据列 + 导出元数据列。元数据包含 `command`、`partial`（完整结果时为 `False`），以及该命令的 `export_meta` 与结论字段（如 `carrier_hz`、`ref_rbw_hz`、`max_abs_delta_db`）。若下游按固定列解析，请注意新增列。

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

> **数值写法**：所有数值参数都支持 `k`/`M`/`G` 后缀与科学计数法，例如 `-b 30k 1M`、`-c 2.4G`、`-c 50e6`、
> `--sg-power -20`。小写 `m` 因易与"毫"混淆而不接受（兆请写 `M`）；非法写法（如 `30x`）会直接报错退出。

> **结果表格**：各命令的「测量结果」以等宽表格输出（数值列右对齐、中文列宽按 2 列计算），便于直接抄录或粘贴到记录表。

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

| 频偏 (Hz) | RBW (Hz) | 相位噪声 (dBc/Hz) |
|-----------|----------|-------------------|
|       100 |     10.0 |            -95.21 |
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

| 设定 RBW (Hz) | 实测 3dB 带宽 (Hz) | 误差 (%) |
|---------------|--------------------|----------|
|           100 |              100.3 |    +0.30 |
|          1000 |              998.5 |    -0.15 |
|         10000 |            10012.0 |    +0.12 |
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

| 设定 RBW (Hz) | -60 dB 带宽 (Hz) |
|---------------|------------------|
|           100 |           1004.7 |
|          1000 |          10120.3 |
|         10000 |         110500.0 |
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

| 设定 span (Hz) |   频率差 (Hz) | 相对误差 (%) | 被校扫频宽度 (Hz) |
|----------------|---------------|--------------|-------------------|
|     1600000000 | 1280000000.00 |        -0.01 |     1600000000.00 |
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

| 衰减 (dB) | marker delta (dB) | 偏差 (dB) |
|-----------|-------------------|-----------|
|         1 |             -1.02 |     -0.02 |
|         2 |             -1.99 |     +0.01 |
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

| 衰减 (dB) | Vm (mV) | 理论 Vn (mV) | 相对误差 (%) |
|-----------|---------|--------------|--------------|
|         4 |  141.09 |       141.09 |       +0.000 |
|         8 |   88.94 |        88.94 |       +0.000 |
|        20 |   22.36 |        22.36 |       +0.000 |
```

---

### 7. 分辨力带宽转换影响 — `rbw-switch` / `分辨力带宽转换影响`

依据 **JJF1396 6.12**：信号源经射频电缆接频谱仪射频输入（图 5）。在固定信号幅度下切换频谱仪分辨力带宽（同时按固定 S/RBW 比率改变扫频宽度），用**标记增量峰值**衡量切换 RBW 带来的幅度变化。理想切换不改变幅度，Δ 应为 0 dB，偏差即"分辨力带宽转换影响"。

**执行步骤（对应规范条款）：**

| 条款 | 程序动作 |
|---|---|
| 6.12.2 | 信号源频率 = 校准信号频率，电平 −20 dBm |
| 6.12.3 | 频谱仪中心 = 校准信号频率，参考电平 −15 dBm，输入衰减 10 dB，RBW = 30 kHz（基准），扫频宽度 = S/RBW × RBW（S/RBW 默认 10，规范取 5~10），VBW/扫描时间自动 |
| 6.12.4 | 峰值标记 → 标记增量（在基准 RBW 的峰值上建立 Δ 参考） |
| 6.12.5 | 逐个改变 RBW（同时按固定 S/RBW 改变扫频宽度），记录标记增量峰值 |
| 6.12.6 | 按附录 A 表 A.11 的 RBW 点集逐个重复（默认为 100 / 300 / 1k / 3k / 10k / 30k / 100k / 300k / 1M Hz，可在 `cal_points.json` 或 `-b` 覆盖） |

> 结论取各切换点 Δ 的**最大绝对值** `max|Δ|`（导出字段 `max_abs_delta_db` 与 `max_abs_delta_at_rbw_hz`）。基准 RBW（30 kHz）自身那一行应接近 0 dB，可作为自参考校验点。

```bash
# 默认：基准 30 kHz、S/RBW = 10、50 MHz 校准信号频率、默认 RBW 点集
sa-cli rbw-switch

# 指定 RBW 点集 / 校准信号频率 / S-RBW 比率
sa-cli rbw-switch -b 1k 3k 10k 30k 100k -c 100e6 --span-ratio 5

# 中文别名 / 导出
sa-cli 分辨力带宽转换影响 -b 30k 100k --output rbw_switch.json
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--rbw-list` | `-b` | float[] | cal_points.json | 待切换的 RBW 列表 (Hz) |
| `--carrier` | `-c` | float | 50e6 | 校准信号频率 (Hz) |
| `--ref-rbw` | | float | 30k | 基准 RBW (Hz)（6.12.3） |
| `--span-ratio` | | float | 10 | 扫频宽度 / RBW 比率（6.12.3 取 5~10） |
| `--ref-level` | `-r` | float | −15 | 参考电平 (dBm)（6.12.3） |
| `--atten` | `-a` | float | 10 | 输入衰减 (dB)（6.12.3） |
| `--sg-power` | | float | −20 | 信号源电平 (dBm)（6.12.2） |
| `--settle` | | float | 0.5 | 每次切换 RBW 后的稳定等待下限 (s) |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**输出示例：**

```
===== 分辨力带宽转换影响（JJF1396 6.12）=====
  校准信号频率: 50000000 Hz
  信号源电平:   -20 dBm（6.12.2）
  参考电平:     -15 dBm，输入衰减 10 dB（6.12.3）
  基准 RBW:     30000.0 Hz，S/RBW = 10.0（6.12.3）
  待切换 RBW:   [100.0, 300.0, 1000.0, 3000.0, 10000.0, 30000.0, 100000.0, 300000.0, 1000000.0]

[1/9] 切换到 RBW=100.0 Hz
  RBW 100.0 Hz（Span 1000 Hz）→ 标记增量峰值 +0.12 dB
...
[6/9] 切换到 RBW=30000.0 Hz（已用 0分42秒 · 预计剩余 0分21秒）
  RBW 30000.0 Hz（Span 300000 Hz）→ 标记增量峰值 +0.00 dB

===== 测量结果 =====

| RBW (Hz) | Span (Hz) | 标记增量峰值 (dB) |
|----------|-----------|-------------------|
|      100 |      1000 |             +0.12 |
|     1000 |     10000 |             -0.35 |
...
  分辨力带宽转换影响（max|Δ|）: 0.350 dB @ RBW=1000.0 Hz
```

---

### 8. 频率读数 — `freq-reading` / `freq` / `频率读数`

频率读数准确性验证：在各校准频率点上，用**频谱仪 marker 峰值读数**核对仪器显示频率。

**执行流程：**

| 步骤 | 做法 |
|---|---|
| 1 | 确定校准频率点，默认 **1 / 10 / 100 / 1000 / 10000 / 26500 MHz**（可在 `cal_points.json` 或 `-f` 覆盖） |
| 2 | 频谱仪中心频率 = 校准频率点，参考电平 **0 dBm** |
| 3 | 信号源输出频率 = 校准频率点，电平 **−1 dBm**，输出开启 |
| 4 | 每个频率点依次设置三个扫频宽度，`peak search` 后读取 marker 频率读数 |
| 5 | 采样点 Points（默认 **1001**）决定显示分辨力 `span/(Points-1)`，读数以仪器显示为准 |

**扫频宽度规则（第 4 步）：**

| 频率点 | 三个扫频宽度 |
|---|---|
| 1 MHz | 0.01 / 0.1 / 1 MHz |
| 10 MHz | 0.1 / 1 / 10 MHz |
| ≥100 MHz（含 100 / 1000 / 10000 / 26500 MHz） | 1 / 10 / 100 MHz |

共 6 × 3 = 18 个测量点。

**显示分辨力与读数口径（第 5 步）**：指令读数的分辨力与频谱仪显示不一致，因此以显示为准——显示分辨力 `= span/(Points-1)`（1001 点即 `span/1000`，例如 span 10 MHz → 0.01 MHz），marker 显示值只能落在显示栅格上（栅格原点为扫频起点 `中心频率 − span/2`）。程序把指令读数按该分辨力量化到栅格后作为显示值参与结论，同时保留指令原始读数与偏差，两者都在导出中。

**显示样式（小数点由分辨力决定）**：导出与日志中的 `*_text` 字段按频谱仪显示样式给出——单位按频率量级自动切换（Hz/kHz/MHz/GHz，可用 `--unit` 强制），小数位数由显示分辨力决定，因此同一行的显示值、分辨力与偏差小数位对齐：

| 频率点 | Span | 显示分辨力 | marker 显示 | 偏差 |
|---|---|---|---|---|
| 100 MHz | 10 MHz | 0.01 MHz | `100.00 MHz` | `+0.00 MHz` |
| 100 MHz | 1 MHz | 0.001 MHz | `100.000 MHz` | `+0.000 MHz` |
| 100 MHz | 100 MHz | 0.1 MHz | `100.0 MHz` | `+0.0 MHz` |
| 1 MHz | 10 kHz | 10 Hz | `1.00000 MHz` | `+0.00000 MHz` |
| 1000 MHz | 100 MHz | 0.0001 GHz | `1.0000 GHz` | `+0.0000 GHz` |

| 导出字段 | 含义 |
|---|---|
| `reading_hz` | 指令读取的 marker 频率（原始值，Hz） |
| `displayed_hz` / `displayed_text` | 量化到显示栅格后的显示值（数值 / 显示样式文本） |
| `error_hz` / `error_text` | `displayed_hz − 标称频率`（**结论以此为准**；`error_text` 带正负号） |
| `raw_error_hz` | `reading_hz − 标称频率` |
| `relative_ppm` | `error_hz / 标称频率 × 10⁶` |
| `resolution_hz` / `resolution_text` | `span/(Points-1)`（数值 / 显示样式文本） |
| `freq_text` / `span_text` | 标称频率与扫频宽度的显示样式文本（与该行小数位一致） |

结论字段：`max_abs_error_hz` 与 `max_abs_error_text`（最大显示偏差）、对应的频率/扫频宽度（数值与文本）、`max_abs_relative_ppm`、`max_error_in_resolution_units`（最大偏差占分辨力的倍数）。

```bash
# 默认频率点与参数
sa-cli freq-reading

# 指定频率点 / 采样点数
sa-cli freq-reading -f 1M 10M 100M 1000M --points-count 1001

# 强制用 MHz 显示（默认按量级自动切换，1000 MHz 会显示为 1.0000 GHz）
sa-cli freq-reading -f 100M 1000M 26500M --unit MHz

# 中文别名 / 导出
sa-cli 频率读数 -f 100M 1000M --output freq_reading.json
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--freq-list` | `-f` | float[] | cal_points.json | 校准频率点列表 (Hz)，支持 `1M`/`1G` 写法 |
| `--ref-level` | `-r` | float | 0 | 参考电平 (dBm) |
| `--sg-power` | | float | −1 | 信号源输出电平 (dBm) |
| `--points-count` | | int ≥ 2 | 1001 | 采样点数 Points（显示分辨力 = span/(Points-1)） |
| `--settle` | | float | 0.5 | 每个扫频点扫描完成后的稳定等待下限 (s) |
| `--unit` | | str | auto | 显示单位：`auto` 按量级自动，或强制 `Hz`/`kHz`/`MHz`/`GHz` |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

> 采样点数通过 `:SWEep:POINts` 下发（`data/spectrum_analyzer.json` 的 `set_sweep_points`）；若你的机型不支持该指令，仪器会保持自身默认点数，此时请用 `--points-count` 填入实际点数以保证分辨力计算正确。

**输出示例：**

```
===== 频率读数准确性验证 =====
  校准频率点:   [1000000.0, 10000000.0, 100000000.0, ...]
  参考电平:     0 dBm，信号源电平 -1 dBm
  采样点数:     1001（显示分辨力 = span/(Points-1)）
  显示单位:     自动（按量级切换）
  扫频宽度规则: 1 MHz→10k/100k/1M；10 MHz→100k/1M/10M；≥100 MHz→1M/10M/100M

[1/18] 频率 1 MHz，扫频宽度 10 kHz
  marker 读数 1000000.0 Hz → 显示 1.00000 MHz（分辨力 0.00001 MHz，偏差 +0.00000 MHz）
...

===== 测量结果 =====

|        频率 |        Span | marker 显示 |  显示分辨力 |         偏差 |
|-------------|-------------|-------------|-------------|--------------|
| 1.00000 MHz | 0.01000 MHz | 1.00000 MHz | 0.00001 MHz | +0.00000 MHz |
| 10.0000 MHz |  1.0000 MHz | 10.0000 MHz |  0.0010 MHz |  +0.0000 MHz |
|  100.00 MHz |   10.00 MHz |  100.00 MHz |    0.01 MHz |    +0.00 MHz |
|  1.0000 GHz |   100.0 MHz |  1.0000 GHz |  0.0001 GHz |  +0.0000 GHz |
...
  最大显示偏差: +0.01 MHz @ 100.00 MHz（Span 10.00 MHz），占分辨力 1.00 倍
  最大相对偏差: +0.100 ppm
```

> 单位与小数位随分辨力变化：同一个 100 MHz 点，Span 1 MHz 显示 `100.000 MHz`、Span 10 MHz 显示 `100.00 MHz`、Span 100 MHz 显示 `100.0 MHz`；1000 MHz 点默认显示 `1.0000 GHz`，需要与记录表统一时用 `--unit MHz`。

---

### 9. 参考电平 — `ref-level` / `reflevel` / `参考电平`

参考电平准确性验证：以 **−10 dBm 为参考点**，逐点改变频谱仪参考电平并用 Delta 标记核对幅度读数变化。

**校准点（默认）：** −10、0、10、−20、−30、−40、−50、−60、−70 dBm（顺序即执行顺序：先参考点，再向上，再向下）。

**仪器设置：**

| 仪器 | 设置 |
|---|---|
| 频谱仪 | 中心频率 = 校准信号频率（默认 50 MHz）、扫频宽度 10 kHz、参考电平 −10 dBm、RBW 1 kHz、VBW 30 Hz、垂直刻度 1 dB/div |
| 信号源 | 输出频率 = 校准信号频率（默认 50 MHz）、初始输出 ≈ −11 dBm |

**执行流程：**

| 步骤 | 做法 |
|---|---|
| 1. 建立参考 | 峰值标记读数应约为信号源初始电平 ±**0.5 dB**；不符则微调信号源直至满足，记录实际设置值 **S0**（后续按 S0 计算，不固定用 −11 dBm）；以当前峰值打开 Delta 标记，Δ 读数应为 0 |
| 2. 逐点计算 | Δ = Lref − (−10)，信号源输出 S = **S0 + Δ**（例：S0 = −11 dBm 时，Lref = 0 → Δ = +10 → S = −1 dBm；Lref = −30 → Δ = −20 → S = −31 dBm） |
| 3. 调整顺序 | **Lref 高于当前参考电平**：先设频谱仪参考电平到 Lref，再设信号源到 S；**低于**：先设信号源到 S，再设频谱仪参考电平到 Lref。两次调整之间间隔 `--step-delay`（默认 **1 s**），避免两台仪器同时切换导致读数未稳定 |
| 4. 读数 | 每次稳定后用峰值搜索将 Delta 活动标记置于新峰值，读取 Δmeas；理论上 Δmeas ≈ Δ，误差 = Δmeas − Δ |
| 5. 记录 | 逐点记录 Lref、S、Δ、Δmeas、误差（导出字段见下） |

**安全与降噪：**

- `--max-sg-power`（默认 10 dBm）：任一校准点需要的信号源输出超过该值即**中止**（退出码 1），避免频谱仪输入过载；中止时已完成点随 `--output` 导出并带 `partial` 标记
- `--average-count` > 1 时，仅对 **Lref ≤ `--average-below`**（默认 −55 dBm）的弱信号点启用 trace 平均（逐次触发扫描填满平均窗口），其余点不受影响

```bash
# 默认点集与参数
sa-cli ref-level

# 自定义点集 / 校准信号频率 / 弱信号平均
sa-cli ref-level -l -10 0 -20 -40 -60 -c 100e6 --average-count 8 --average-below -55

# 中文别名 / 导出
sa-cli 参考电平 -l -10 0 10 --output ref_level.json
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--levels` | `-l` | float[] | cal_points.json | 参考电平点列表 (dBm)，允许 0 与负值 |
| `--carrier` | `-c` | float | 50e6 | 校准信号频率 (Hz) |
| `--span` | | float | 10k | 扫频宽度 (Hz) |
| `--rbw` | | float | 1k | 分辨力带宽 (Hz) |
| `--vbw` | | float | 30 | 视频带宽 (Hz) |
| `--sg-power` | | float | −11 | 信号源初始输出电平 (dBm) |
| `--tolerance` | | float | 0.5 | 参考建立容差 (dB) |
| `--max-sg-power` | | float | 10 | 信号源输出安全上限 (dBm) |
| `--average-count` | | int ≥ 1 | 1 | 弱信号点 trace 平均次数（1 = 不平均） |
| `--average-below` | | float | −55 | 参考电平不高于该值时启用平均 (dBm) |
| `--step-delay` | | float | 1.0 | 两台仪器调整之间的间隔 (s)；0 = 不额外等待 |
| `--settle` | | float | 0.5 | 每次调整后的稳定等待下限 (s) |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**导出字段（每点）：** `ref_level_dbm`、`sg_power_dbm`（实际 S）、`expected_delta_db`（Δ）、`measured_delta_db`（Δmeas）、`error_db`（误差）、`s0_dbm`（参考建立时的实际信号源电平）。结论字段：`s0_dbm`、`max_abs_error_db` 与 `max_abs_error_at_ref_level_dbm`。

**输出示例：**

```
===== 参考电平校准（参考点 -10 dBm）=====
  校准信号频率: 50000000 Hz，扫频宽度 10000 Hz
  RBW / VBW:    1000 Hz / 30 Hz，垂直刻度 1 dB/div
  参考电平点:   [-10, 0, 10, -20, -30, -40, -50, -60, -70] dBm
  信号源初始:   -11.0 dBm（±0.5 dB 内微调并记录实际 S0）
  安全上限:     信号源输出不超过 10.0 dBm
  弱信号平均:   关闭
  调整间隔:     两台仪器之间 1.0 s（顺序：升高先频谱仪、降低先信号源）

  参考建立: 峰值读数 -11.300 dBm → 信号源实际设置 S0 = -11.000 dBm
  Lref -10 dBm → S = -11.00 dBm，Δ = +0.00 dB，Δmeas = +0.000 dB（误差 +0.000 dB）
  Lref +0 dBm → S = -1.00 dBm，Δ = +10.00 dB，Δmeas = +10.015 dB（误差 +0.015 dB）
  ...

===== 测量结果 =====

| 参考电平 (dBm) | 信号源 S (dBm) | Δ (dB) | Δmeas (dB) | 误差 (dB) |
|----------------|----------------|--------|------------|-----------|
|            -10 |         -11.00 |  +0.00 |     +0.000 |    +0.000 |
|              0 |          -1.00 | +10.00 |    +10.015 |    +0.015 |
|             10 |           9.00 | +20.00 |    +19.985 |    -0.015 |
|            -20 |         -21.00 | -10.00 |     -9.990 |    +0.010 |
|            -30 |         -31.00 | -20.00 |    -20.008 |    -0.008 |
|            -70 |         -71.00 | -60.00 |    -60.020 |    -0.020 |
  参考建立实际信号源电平 S0: -11.000 dBm
  最大读数偏差: -0.020 dB @ -70 dBm
```

### 10. 输入衰减器转换影响 — `input-atten` / `atten` / `输入衰减` / `输入衰减器转换影响`

输入衰减器转换影响校准：以 **10 dB 输入衰减为参考点**，逐档改变输入衰减，同时按同一步进抬高参考电平与信号源输出，用 Delta 标记核对幅度读数变化是否等于衰减步进。

**校准点（默认）：** 10、20、30、40、50、60、70 dB（顺序即执行顺序，10 dB 为参考点）。

**对应关系：** 输入衰减 A → 参考电平 Lref = −60 + (A − 10) dBm → 信号源设置 S = **S0 + (A − 10)** → 理论 ΔLm = A − 10 dB。

| 输入衰减 | 参考电平 | 信号源设置 | 理论 ΔLm |
|---|---|---|---|
| 10 dB | −60 dBm | S = S0 | 0 dB |
| 20 dB | −50 dBm | S = S0 + 10 dB | +10 dB |
| 30 dB | −40 dBm | S = S0 + 20 dB | +20 dB |
| 40 dB | −30 dBm | S = S0 + 30 dB | +30 dB |
| 50 dB | −20 dBm | S = S0 + 40 dB | +40 dB |
| 60 dB | −10 dBm | S = S0 + 50 dB | +50 dB |
| 70 dB | 0 dBm | S = S0 + 60 dB | +60 dB |

**仪器设置：**

| 仪器 | 设置 |
|---|---|
| 频谱仪 | 中心频率 = 校准信号频率（默认 50 MHz）、扫频宽度 500 Hz、RBW 1 kHz、垂直刻度 1 dB/div、参考电平 −60 dBm（参考点）、迹线平均 10 次、**手动输入衰减**（`:POWer:ATTenuation:AUTO OFF`） |
| 信号源 | 输出频率 = 校准信号频率（默认 50 MHz）、初始输出 ≈ −62 dBm |

**执行流程：**

| 步骤 | 做法 |
|---|---|
| 1. 建立参考 | 输入衰减置 10 dB、参考电平置 −60 dBm，打开峰值标记与迹线平均；峰值读数应约为信号源初始电平 ±**0.5 dB**，不符则微调信号源直至满足，记录实际设置值 **S0**（后续一律按实际 S0 计算，不固定用 −62 dBm）；以当前峰值打开 Delta 标记，Δ 读数应为 0 |
| 2. 逐点设置 | 对每个衰减档 A：先设输入衰减 A、再设参考电平 Lref、再设信号源 S = S0 + (A − 10)（见「调整顺序」） |
| 3. 调整顺序 | **衰减升高**：先加输入衰减 → 再抬高参考电平 → 最后加信号源输出；**衰减降低**：先降信号源输出 → 再降低参考电平 → 最后减输入衰减。「衰减与参考电平」和「信号源输出」之间间隔 `--step-delay`（默认 **1 s**） |
| 4. 读数 | 每次改变设置后触发扫描并**填满平均窗口**（默认 10 次）再读数；稳定后**不做 peak search**，直接读取 Delta 标记读数 ΔLm |
| 5. 记录 | 逐点记录输入衰减、参考电平、实际信号源设置 S、理论 ΔLm、实测 ΔLm、误差 = 实测 ΔLm − 理论 ΔLm（导出字段见下） |

**安全：**

- `--max-sg-power`（默认 10 dBm）：任一校准点需要的信号源输出超过该值即**中止**（退出码 1），避免频谱仪输入过载；中止时已完成点随 `--output` 导出并带 `partial` 标记
- 参考点 70 dB / 0 dBm 时信号源输出约为 S0 + 60 dB（默认点集与默认安全上限内可完整跑完）；频谱仪输入端的实际耐受限仍由操作者确认
- 测量结束后频谱仪保持**手动衰减**与最后一个衰减档，不恢复自动衰减；信号源关闭 RF

```bash
# 默认点集与参数
sa-cli input-atten

# 自定义衰减点 / 校准信号频率 / 调整间隔
sa-cli input-atten -a 10 20 30 40 50 -c 100e6 --step-delay 2

# 关闭迹线平均 / 中文别名 / 导出
sa-cli 输入衰减 -a 10 20 --average-count 1 --output input_atten.json
```

**参数：**

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--attens` | `-a` | float[] | cal_points.json | 输入衰减校准点列表 (dB)，允许 0（不衰减） |
| `--carrier` | `-c` | float | 50e6 | 校准信号频率 (Hz) |
| `--span` | | float | 500 | 扫频宽度 (Hz) |
| `--rbw` | | float | 1k | 分辨力带宽 (Hz) |
| `--ref-level` | `-r` | float | −60 | 参考点（参考输入衰减）对应的参考电平 (dBm) |
| `--ref-atten` | | float | 10 | 参考点输入衰减 (dB)；参考电平 = 该点参考电平 + (A − 参考衰减) |
| `--sg-power` | | float | −62 | 信号源初始输出电平 (dBm) |
| `--tolerance` | | float | 0.5 | 参考建立容差 (dB) |
| `--max-sg-power` | | float | 10 | 信号源输出安全上限 (dBm) |
| `--average-count` | | int ≥ 1 | 10 | 迹线平均次数（1 = 不平均） |
| `--step-delay` | | float | 1.0 | 衰减/参考电平调整与信号源调整之间的间隔 (s)；0 = 不额外等待 |
| `--settle` | | float | 0.5 | 每次调整后的稳定等待下限 (s) |
| `--sg-addr` | | str | GPIB0::19 | 信号源 VISA 地址 |
| `--sa-addr` | | str | GPIB0::18 | 频谱仪 VISA 地址 |

**导出字段（每点）：** `atten_db`、`ref_level_dbm`、`sg_power_dbm`（实际 S）、`expected_delta_db`（理论 ΔLm）、`measured_delta_db`（实测 ΔLm）、`error_db`（误差）、`s0_dbm`（参考建立时的实际信号源电平）。结论字段：`s0_dbm`、`max_abs_error_db` 与 `max_abs_error_at_atten_db`。

**输出示例：**

```
===== 输入衰减器转换影响校准（参考点 10 dB）=====
  校准信号频率: 50000000 Hz，扫频宽度 500 Hz
  RBW / 垂直刻度: 1000 Hz / 1 dB/div
  参考点状态:   输入衰减 10 dB + 参考电平 -60 dBm
  衰减校准点:   [10, 20, 30, 40, 50, 60, 70] dB
  信号源初始:   -62.0 dBm（±0.5 dB 内微调并记录实际 S0）
  安全上限:     信号源输出不超过 10.0 dBm
  迹线平均:     10 次
  调整间隔:     1.0 s（顺序：衰减升高先加衰减与参考电平，降低先降信号源）

  参考建立: 输入衰减 10 dB / 参考电平 -60 dBm，峰值读数 -62.040 dBm → 信号源实际设置 S0 = -61.960 dBm
  衰减 10 dB（Lref -60 dBm，S = -61.96 dBm）→ Δ = +0.00 dB，ΔLm = +0.000 dB（误差 +0.000 dB）
  衰减 20 dB（Lref -50 dBm，S = -51.96 dBm）→ Δ = +10.00 dB，ΔLm = +10.012 dB（误差 +0.012 dB）
  ...

===== 测量结果 =====

| 输入衰减 (dB) | 参考电平 (dBm) | 信号源 S (dBm) | Δ理论 (dB) | ΔLm (dB) | 误差 (dB) |
|---------------|----------------|----------------|------------|----------|-----------|
|            10 |            -60 |         -61.96 |      +0.00 |   +0.000 |    +0.000 |
|            20 |            -50 |         -51.96 |     +10.00 |  +10.012 |    +0.012 |
|            30 |            -40 |         -41.96 |     +20.00 |  +19.988 |    -0.012 |
|            40 |            -30 |         -31.96 |     +30.00 |  +30.005 |    +0.005 |
|            50 |            -20 |         -21.96 |     +40.00 |  +40.021 |    +0.021 |
|            60 |            -10 |         -11.96 |     +50.00 |  +49.980 |    -0.020 |
|            70 |              0 |          -1.96 |     +60.00 |  +60.018 |    +0.018 |
  参考建立实际信号源电平 S0: -61.960 dBm
  最大读数偏差: +0.021 dB @ 50 dB 输入衰减
```

## 架构说明

### 仪器基类 `Instrument`（`src/sa_cli/instruments/base.py`）

从 JSON 文件加载 SCPI 指令集，通过闭包工厂 `_create_methods()` 动态生成实例方法。新增仪器指令只需编辑 JSON，无需改 Python 代码。

```python
class SpectrumAnalyzer(Instrument):
    def __init__(self, resource_address, rm=None):
        super().__init__(resource_address, "spectrum_analyzer.json", rm)
        self.instr.timeout = 60000  # 频谱仪超时 60s（与 OPC 等待上限一致）
```

信号发生器超时放宽至 15s（`src/sa_cli/instruments/devices.py`），以覆盖频率/电平稳定等待；`visa_session` 上下文管理器在退出时（无论正常或异常）会强制发送 `rf_off`，确保测量结束后 RF 输出关闭。

### 公共搜索函数 `_find_edge`（`src/sa_cli/measurements/bandwidth.py`）

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

所有"等待仪器就绪"均基于 IEEE 488.2 标准通用命令 `*OPC?`（跨厂商兼容，PSA 系列与 N5183B/E8257D/E4438C 均支持），由 `src/sa_cli/measurements/common.py` 中三个帮助函数实现：

- **`_wait_opc(instr, min_sleep, timeout_s)`** — 先保底等待 `min_sleep`（覆盖 preset 内部校准等 `*OPC?` 未跟踪的操作），再轮询 `*OPC?` 返回 1；超时或通信失败抛出异常并停止当前校准点；单次 VISA 查询超时受剩余 OPC 预算限制，结束后恢复原 VISA 超时。
- **`_wait_sweep(spec_an, min_sleep, timeout_s)`** — 等待频谱仪完成一次扫描：切单次扫描（`:INITiate:CONTinuous OFF`）→ 触发（`:INITiate:IMMediate`，即 `init_sweep` action）→ `*OPC?` → 恢复连续扫描。**连续扫描模式下 `*OPC?` 语义不可靠（可能立即返回或永久阻塞），必须搭配单次扫描模式使用**。
- **`_opc_done(instr)`** — `*OPC?` 返回 1 的判定，用于判定完成状态；实际等待流程遇到 I/O 异常会中止当前校准点。

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


## 结果可靠性与输入校验

- 数值参数和仪器数值响应必须有限；拒绝 `nan`、`inf` 和溢出数值。校准点必须为非空、不重复的正数列表，JSON 配置同样受校验。
- OPC 超时、通信失败、边沿搜索或峰值调整未收敛时，中止测量并返回非零退出码。已完成校准点仍按部分结果机制导出。
- CSV 每行包含命令元数据、汇总字段和 `partial` 标记；`True` 表示结果不完整，`False` 表示完整结果。JSON 保留原有结构。
- 输出扩展名和父目录在连接仪器之前检查。JSON/CSV 先写入同目录临时文件，成功后替换目标文件；写入失败保留已有文件。
- `--dry-run` 使用模拟读数，跳过峰值收敛判定；输出不能作为实测结果。每个仪器实例持有独立等待策略，不修改全局等待函数，允许同一进程交替执行 dry-run 和真实测量。


## Python 调用与会话边界

测量函数只负责测量，RF 关闭和资源释放统一由 `visa_session` 管理。直接调用
Python API 时也应放在会话上下文中；正常退出、测量异常和第二台仪器连接失败
都会尝试关闭信号源 RF。RF 关闭失败会记录警告，不覆盖原测量异常。

```python
from sa_cli import config
from sa_cli.instruments import visa_session
from sa_cli.measurements import cal_rbw

with visa_session(config.sg_addr(), config.sa_addr()) as (sig, spec):
    results = cal_rbw(spec, sig, rbw_list=[100, 1000])
```

等待策略通过 `visa_session(..., sleep=callback)` 或
`sa_cli.cli.main.main(argv, sleep=callback)` 显式注入，默认使用真实等待；
`dry_run=True` 始终使用不等待策略。测试可注入记录函数，实际测量保留默认值。

## 构建与验证

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m pytest tests/integration -q
python -m pip wheel . --no-deps -w dist
```

发布前在独立环境安装 wheel，并切换到仓库外运行
`sa-cli rbw-switch -b 100 1000 --dry-run`，验证入口和内置 JSON 资源完整。

## 版本与变更

| 版本 | 布局 | 说明 |
|---|---|---|
| **0.2.0**（当前） | `src/sa_cli/` 包布局 | 结构重构，并强化失败判定、导出与配置校验 |
| 0.1.0 | 仓库根顶层模块 | 首个版本（提交 `7cc21e9`） |

完整变更与**行为变化清单**见 [CHANGELOG.md](CHANGELOG.md)。升级时请特别留意：OPC 等待超时会中止当前校准点、边沿/峰值不收敛即报错、CSV 增加元数据列、`cal_points.json` 拒绝重复点、`SA_CLI_DATA_DIR` 指向缺失目录不再回退到包内数据。
