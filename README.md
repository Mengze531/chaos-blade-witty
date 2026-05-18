# ChaosBlade + witty 自动化评测工具

将 [ChaosBlade](https://github.com/chaosblade-io/chaosblade)（混沌工程故障注入）与 witty（AI 多智能体诊断系统）集成，实现**故障注入 → 日志采集 → AI 诊断 → 根因分析 → 报告生成**的全自动化闭环评测。

## 运行效果示例

```
=======================================================
  ChaosBlade + witty Agent Auto Benchmark
  1 scenario(s): cpu
=======================================================

=======================================================
  CPU overload inject
=======================================================

  [Step 1] Baseline (before injection)
  [Step 2] ChaosBlade inject...
    Command: /opt/chaosblade-1.8.0/blade create cpu fullload --cpu-percent 70 --timeout 20
    Result: {"code":200,"success":true,"result":"48135fe843ed4e7c"}
  [Step 3] Collect diagnosis logs...
    Waiting 25s auto destroy...
  [Step 4] Agent pipeline...
  ...
  [RCA Report saved] bench_output/cpu_20260517_212834/baize_rca_report.md
  [OK] scenario 'cpu' complete

  All 1/1 complete
  Report: bench_output/chaos_witty_agent_skill_report.md
```

注入成功时的指标（CPU 过载场景）：
- 用户态 CPU (`cpu_us`) 从正常升至 **59.2%**，空闲 (`cpu_idle`) 降至 **36.9%**
- 系统负载 (`load_1min`) 飙升至 **2.73**
- 诊断 agent 自动捕获 `chaos_os` 异常进程（CPU 占用 960%）

## 环境要求

| 组件 | 要求 | 说明 |
|------|------|------|
| Docker Desktop | >= 4.x | 需保持运行状态（[下载](https://www.docker.com/products/docker-desktop/)） |
| WSL 2 | Ubuntu 22.04 | Docker Desktop 的默认后端（[安装指南](https://learn.microsoft.com/zh-cn/windows/wsl/install)） |
| Python | >= 3.6 | 用于运行评测脚本 |
| ChaosBlade | v1.8.0 | **已预装**在 `chaosblade-demo` Docker 容器中，无需手动安装 |
| witty 诊断脚本 | 最新版 | 位于 `C:\Users\86188\.config\opencode\skills\offline-disk-fault-diagnosis\scripts` |

### 前置检查清单

1. **Docker Desktop 正在运行**（系统托盘可见鲸鱼图标）
2. **WSL Ubuntu 已安装且运行中**（`wsl -l -v` 查看状态）
3. **chaosblade-demo 容器存在**（若不存在需先构建）
4. **witty 诊断脚本存在**（路径见上方表格）

### Docker 容器构建（首次使用）

如果本地没有 `chaosblade-demo` 容器，需要先构建：

```powershell
# 1. 拉取 Ubuntu 22.04 镜像
docker pull ubuntu:22.04

# 2. 创建容器并安装 ChaosBlade
docker run -itd --name chaosblade-demo ubuntu:22.04
docker exec chaosblade-demo apt update
docker exec chaosblade-demo apt install -y curl wget tar procps iproute2 stress-extra sysstat
docker exec chaosblade-demo bash -c "
  cd /opt &&
  curl -LO https://github.com/chaosblade-io/chaosblade/releases/download/v1.8.0/chaosblade-1.8.0-linux-amd64.tar.gz &&
  tar -xzf chaosblade-1.8.0-linux-amd64.tar.gz &&
  rm chaosblade-1.8.0-linux-amd64.tar.gz
"
```

## 快速开始

### 方法一：交互式菜单（推荐）

```powershell
cd G:\chaos-blade-witty-benchmark
python run.py
```

菜单选项：
1. 自动检查环境（Docker 容器、ChaosBlade、witty 脚本）
2. 选择故障场景编号
3. 自动运行并生成报告

### 方法二：命令行一键执行

```powershell
# 运行单个场景
python run.py cpu               # CPU 过载 70%，20s
python run.py disk_io            # 磁盘 IO 写入 50MB，15s
python run.py mem                # 内存负载 60%，20s
python run.py process            # 进程终止（SIGTERM）
python run.py disk_fill          # 磁盘写满 80%，15s

# 运行全部 5 个场景（约 3 分钟）
python run.py --all

# 查看可用场景
python run.py --list
```

### 方法三：直接调用底层框架

```powershell
cd G:\chaos-blade-witty-benchmark\scripts

# 全部场景（agent skill 版本，推荐）
python chaos_witty_agent_skill.py

# 指定场景
python chaos_witty_agent_skill.py -s cpu

# 备选框架
python chaos_witty_bench.py --scenario cpu

# 查看可用场景
python chaos_witty_agent_skill.py --list
```

## 可用故障场景

| 编号 | 场景 | 注入命令 | 注入时长 | 采集指标数 |
|------|------|----------|----------|-----------|
| 1 | CPU 过载 70% | `blade create cpu fullload --cpu-percent 70 --timeout 20` | 20s | 9 个（top, loadavg, mpstat 等） |
| 2 | 磁盘 IO 写入 50MB | `blade create disk burn --write --size 50 --timeout 15` | 15s | 7 个（iostat, diskstats, lsblk 等） |
| 3 | 进程终止 SIGTERM | `blade create process kill --process sleep --signal 15` | 即时 | 5 个（ps_before, ps_after 等） |
| 4 | 磁盘写满 80% | `blade create disk fill --path /tmp --percent 80 --timeout 15` | 15s | 5 个（df, du_top 等） |
| 5 | 内存负载 60% | `blade create mem load --mode ram --mem-percent 60 --timeout 20` | 20s | 8 个（meminfo, vmstat, dmesg_oom 等） |

## 输出产物

运行完成后，所有结果位于 `bench_output/` 目录：

```
bench_output/
├── chaos_witty_agent_skill_report.md     ← 汇总评测报告（含全部场景对比）
├── cpu_20260517_212834/                   ← 每个场景独立目录
│   ├── baize_rca_report.md               ← Baize Agent 生成的 RCA 诊断报告
│   ├── baseline.txt                      ← 注入前基线数据
│   ├── inject_result.txt                 ← ChaosBlade 注入结果（JSON）
│   └── diagnosis/
│       ├── infocollect_logs/             ← 系统诊断指标（9 个文件）
│       │   ├── top.txt                   ← 进程快照
│       │   ├── loadavg.txt               ← 系统负载
│       │   ├── cpu_stat.txt              ← CPU 统计
│       │   ├── memory.txt                ← 内存信息
│       │   ├── dmesg.log                 ← 内核日志
│       │   └── ...
│       └── messages/                     ← 系统消息日志
│           └── dmesg.log                 ← 内核日志副本
```

### 汇总报告示例

```markdown
| Scenario | Fault Type | Inject | Diagnose | UID |
|----------|------------|--------|----------|-----|
| cpu      | CPU overload inject | [OK] | [OK] | 48135fe843ed4e7c |

**Key Metrics**:
| Metric | Value |
|--------|-------|
| load_1min | 2.73 |
| cpu_us | 59.2 |
| cpu_idle | 36.9 |
```

### RCA 报告示例

诊断证据自动提取：
- 异常进程：`chaos_os`（CPU 占用 960%）
- 系统负载：`2.73 0.60 0.20`
- 证据验证：时间线 → PASS、身份匹配 → PASS、系统排他 → PASS

## 架构说明

### 工作流

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  Step 1  │    │  Step 2  │    │  Step 3  │    │  Step 4  │    │  Step 5  │
│  基线采集 │───→│ 故障注入 │───→│ 日志采集 │───→│  AI 诊断 │───→│ 报告生成 │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
                                              │
                                    ┌─────────┴─────────┐
                                    │   5 Agent Pipeline  │
                                    ├───────────────────┤
                                    │ Fuxi   规划扫描     │
                                    │ Dayu   任务编排     │
                                    │ Kuafu  执行诊断     │
                                    │ Baize  根因分析     │
                                    │ Nuwa   修复建议     │
                                    └───────────────────┘
```

### 项目结构

```
chaos-blade-witty-benchmark/
├── run.py                               # 交互式一键入口（推荐）
├── scripts/
│   ├── chaos_witty_agent_skill.py       # 主框架：5 Agent AI 诊断流水线
│   └── chaos_witty_bench.py             # 备选框架：传统脚本评测
├── bench_output/                        # 评测结果输出目录
├── experiments/                         # Chaos Toolkit 实验定义 JSON
├── sample_logs/                         # 示例诊断日志
│   ├── ibmc_logs/                       # 硬件日志
│   ├── infocollect_logs/                # 系统指标
│   └── messages/                        # 内核日志
├── docs/                                # 故障注入测试文档
│   ├── manba_fault_injection_report.md  # Manba API 网关故障注入报告
│   └── manba_rca_report.md              # Manba RCA 报告
└── manba/                               # Manba 相关产物（目前为空）
```

## 常见问题

### Docker 连接失败

```
error during connect: open //./pipe/dockerDesktopLinuxEngine
```

**解决**：启动 Docker Desktop，等待右下角图标变为稳定状态（无动画），然后重试。

### 容器不存在

```
Error: No such container: chaosblade-demo
```

**解决**：参考上方的"容器构建"章节创建容器。

### ChaosBlade 注入失败

故障场景运行后 `inject` 状态为 `[FAIL]`。

常见原因：
- 容器内权限不足（`--privileged` 未设置）
- 目标进程不存在（如 `process` 场景需先启动 `sleep` 进程）
- Docker 版本与 ChaosBlade 不兼容

**排查**：查看 `bench_output/{场景}_{时间戳}/inject_result.txt` 中的错误信息。

### witty 诊断脚本缺失

```
[ERROR] witty scripts not found
```

**解决**：确保 `C:\Users\86188\.config\opencode\skills\offline-disk-fault-diagnosis\scripts\` 目录存在且包含以下文件：
- `diagnose_summary.py`
- `diagnose_ibmc.py`
- `diagnose_infocollect.py`
- `diagnose_messages.py`

如果不用于 witty 诊断（仅做故障注入），可以修改 `run.py:66` 中的路径或注释掉该检查。

## 参考

- [ChaosBlade 官方文档](https://chaosblade.io/)
- [ChaosBlade GitHub](https://github.com/chaosblade-io/chaosblade)
- [Manba API Gateway (fagongzi/gateway)](https://github.com/fagongzi/gateway)
- [Chaos Toolkit](https://chaostoolkit.org/)
