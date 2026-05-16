# ChaosBlade + witty 自动化评测工具

## 三步上手

### 方法一：交互式菜单（推荐）

```powershell
# 第一步：双击或运行
.\run_bench.ps1
```

然后按菜单提示操作：1.自动检查环境 → 2.选择场景编号 → 3.自动出报告

### 方法二：命令行一键执行

```powershell
# 全部5个场景（约3分钟）
.\run_bench.ps1 --all

# 单个场景
.\run_bench.ps1 cpu
.\run_bench.ps1 disk_io
.\run_bench.ps1 mem

# 查看列表
.\run_bench.ps1 --list
```

### 方法三：Python 直接调用

```powershell
python chaos_witty_agent_skill.py
python chaos_witty_agent_skill.py -s cpu
```

## 产出物

运行完成后，所有产出在 `bench_output/` 目录：

| 文件 | 说明 |
|------|------|
| `bench_output/chaos_witty_agent_skill_report.md` | 汇总评测报告 |
| `bench_output/{场景}_{时间戳}/baize_rca_report.md` | 每个场景的 RCA 报告 |
| `bench_output/{场景}_{时间戳}/diagnosis/` | 诊断日志数据 |

## 当前可用场景

| 编号 | 场景 | 注入时长 | 采集数据 |
|------|------|----------|----------|
| 1 | CPU 过载 70% | 20s | 9 个指标文件 |
| 2 | 磁盘 IO 写入 50MB | 15s | 7 个指标文件 |
| 3 | 进程杀 SIGTERM | 即时 | 5 个指标文件 |
| 4 | 磁盘写满 80% | 15s | 5 个指标文件 |
| 5 | 内存负载 60% | 20s | 8 个指标文件 |

## 环境要求

- Docker Desktop（运行中）
- Python 3.6+
- 无需手动安装 ChaosBlade（已预装在 Docker 容器中）
