# 硬盘故障诊断排查计划

## 基本信息

| 项目 | 内容 |
|------|------|
| **故障描述** | 2026-03-05 14:31 前最近一次硬盘故障 |
| **日志路径** | G:\chaostoolkit\sample_logs |
| **计划生成时间** | 2026-05-05 |

## 故障现象

日志全景扫描发现：
- **iBMC 日志**：时间范围 2026-03-05 00:20:00 ~ 14:30:00，检测到 Drive Fault 相关事件
- **InfoCollect 日志**：SMART 信息和 SAS/RAID 拓扑数据可用
- **OS Messages**：时间范围 2026-03-05 00:26:22 ~ 14:12:20，smartd 告警和 I/O error 记录

## 候选根因假设

| # | 假设 | 可能性 |
|---|------|--------|
| H1 | **硬盘物理介质损坏**（坏道）— SMART 显示 Reallocated_Sector_Ct 和 Current_Pending_Sector 异常 | ★★★★★ |
| H2 | **SAS 链路/背板故障** — 检查 iBMC 中是否有 PHY Reset、链路重置记录 | ★★★ |
| H3 | **RAID 控制器/缓存问题** — 检查 RAID 卡状态和电池备份单元 | ★★ |

## 分层排查步骤

### Step 0：故障日志采集 ✅ 已完成
- 运行 `diagnose_summary.py` 获取全景概览
- 检测到三层日志均存在，时间范围集中

### Step 1：场景分类
- 执行命令：`diagnose_ibmc.py -o` + `diagnose_infocollect.py -o` + `diagnose_messages.py -o`
- 目标：确定故障场景标签（DISK_HARDWARE_FAILURE / DISK_LINK_ISSUE / DISK_RAID_ERROR）

### Step 2：深入分析
- **iBMC 分析**：`diagnose_ibmc.py` -k "Drive" "Fault" "Failed"
- **InfoCollect 分析**：`diagnose_infocollect.py` -k "sdi" "FAILED" "Pending"
- **OS Messages 分析**：`diagnose_messages.py` -k "I/O error" "sdi" "XFS"

### Step 3：根因校验
- 交叉验证三层证据的一致性
- 输出根因证据校验表（E1 时序连续性 / E2 物理同一性 / E3 现象排他性）

### Step 4：输出分析报告
- 汇总证据链，生成结构化 RCA 报告

```json
{
  "plan_path": "G:\\chaostoolkit\\sample_logs\\fuxi_plan.md",
  "plan_version": "1.0",
  "plan_agent": "Fuxi-Sub",
  "fault_category": "disk_hardware",
  "log_root": "G:\\chaostoolkit\\sample_logs",
  "skills_required": ["offline-disk-fault-diagnosis"]
}
```
