#!/usr/bin/env python3
"""
ChaosBlade + witty-diagnosis-agent 自动化评测框架
=============================================
功能：
  1. 自动执行多个故障注入场景（CPU/磁盘/进程/内存等）
  2. 自动采集系统诊断日志
  3. 自动调用 witty 诊断脚本进行分析
  4. 自动生成结构化评测报告

使用方法：
  python chaos_witty_bench.py                     # 运行全部场景
  python chaos_witty_bench.py --scenario cpu      # 运行指定场景
  python chaos_witty_bench.py --list              # 列出可用场景
"""

import os
import sys
import subprocess
import time
import json
import re
import shutil
from datetime import datetime

os.environ["PYTHONIOENCODING"] = "utf-8"

# ==================== 配置 ====================
CONTAINER = "chaosblade-demo"
WORK_DIR = r"G:\chaostoolkit\bench_output"
SKILL_DIR = r"C:\Users\86188\.config\opencode\skills\offline-disk-fault-diagnosis\scripts"
SUMMARY_PY = os.path.join(SKILL_DIR, "diagnose_summary.py")
IBMC_PY = os.path.join(SKILL_DIR, "diagnose_ibmc.py")
INFOCOLLECT_PY = os.path.join(SKILL_DIR, "diagnose_infocollect.py")
MESSAGES_PY = os.path.join(SKILL_DIR, "diagnose_messages.py")
BLADE_BIN = "/opt/chaosblade-1.8.0/blade"

# ==================== 日志 ====================
LOG_FILE = None

def log(msg):
    safe = msg.encode('ascii', errors='replace').decode('ascii')
    s = f"[{datetime.now().strftime('%H:%M:%S')}] {safe}"
    print(s)
    if LOG_FILE:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(s + "\n")

# ==================== 工具函数 ====================
def run_cmd(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() + "\n" + r.stderr.strip()
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR] {e}"

def docker_exec(cmd, timeout=60):
    full = f"docker exec {CONTAINER} bash -c \"{cmd}\""
    return run_cmd(full, timeout)

def docker_cp(src, dst, timeout=30):
    full = f"docker cp {CONTAINER}:{src} \"{dst}\""
    return run_cmd(full, timeout)

# ==================== 故障场景定义 ====================
SCENARIOS = {}

SCENARIOS["cpu"] = {
    "name": "CPU 过载注入",
    "description": "通过 ChaosBlade 对系统注入 CPU 百分比负载，模拟计算密集型任务",
    "blade_cmd": f"{BLADE_BIN} create cpu fullload --cpu-percent 70 --timeout 20",
    "witty_skills": ["offline-disk-fault-diagnosis", "online-cpu-scheduling-diagnosis"],
    "collect_cmds": {
        "dmesg.log": "dmesg",
        "top.txt": "top -bn1",
        "loadavg.txt": "cat /proc/loadavg",
        "cpu_stat.txt": "cat /proc/stat | head -n 17",
        "top_processes.txt": "ps aux --sort=-%cpu",
        "memory.txt": "free -h",
        "uptime.txt": "uptime",
        "mpstat.txt": "mpstat -P ALL 1 1 2>/dev/null || echo no_mpstat",
        "lscpu.txt": "lscpu 2>/dev/null || echo no_lscpu",
    },
    "diag_keywords": {"infocollect": ["CPU", "load"], "messages": ["CPU|load|chaos_os|error"]},
}

SCENARIOS["disk_io"] = {
    "name": "磁盘 IO 写入负载注入",
    "description": "通过 ChaosBlade 对磁盘注入持续写入 IO 负载，模拟 IO 密集型任务",
    "blade_cmd": f"{BLADE_BIN} create disk burn --write --size 50 --timeout 15",
    "witty_skills": ["offline-disk-fault-diagnosis", "online-file-system-fault-diagnosis"],
    "collect_cmds": {
        "dmesg.log": "dmesg",
        "iostat.txt": "iostat -x 1 5 2>/dev/null || echo no_iostat",
        "top.txt": "top -bn1",
        "diskstats.txt": "cat /proc/diskstats",
        "df.txt": "df -h",
        "loadavg.txt": "cat /proc/loadavg",
        "lsblk.txt": "lsblk 2>/dev/null || echo no_lsblk",
    },
    "diag_keywords": {"infocollect": ["disk", "write", "io"], "messages": ["I/O error|disk|sda|sdb|error"]},
}

SCENARIOS["process"] = {
    "name": "进程终止注入",
    "description": "通过 ChaosBlade 向指定进程发送信号，模拟进程崩溃",
    "blade_cmd": f"{BLADE_BIN} create process kill --process sleep --signal 15",
    "witty_skills": ["offline-disk-fault-diagnosis", "system-resource-diagnosis"],
    "collect_cmds": {
        "dmesg.log": "dmesg",
        "top.txt": "top -bn1",
        "ps_before.txt": "ps aux | grep sleep | grep -v grep",
        "ps_after.txt": "ps aux | head -30",
        "loadavg.txt": "cat /proc/loadavg",
    },
    "diag_keywords": {"infocollect": ["process", "sleep"], "messages": ["killed|signal|process|error"]},
}

SCENARIOS["disk_fill"] = {
    "name": "磁盘写满注入",
    "description": "通过 ChaosBlade 填充磁盘空间到指定百分比，模拟磁盘空间耗尽",
    "blade_cmd": f"{BLADE_BIN} create disk fill --path /tmp --percent 80 --timeout 15",
    "witty_skills": ["offline-disk-fault-diagnosis", "online-file-system-fault-diagnosis"],
    "collect_cmds": {
        "dmesg.log": "dmesg",
        "df.txt": "df -h",
        "top.txt": "top -bn1",
        "du_top.txt": "du -sh /*.log* /*.dat* /tmp/*.log* /tmp/*.dat* 2>/dev/null | sort -rh | head -10",
        "loadavg.txt": "cat /proc/loadavg",
    },
    "diag_keywords": {"infocollect": ["disk", "space", "fill"], "messages": ["disk|space|fill|error|I/O"]},
}

SCENARIOS["mem"] = {
    "name": "内存负载注入",
    "description": "通过 ChaosBlade 分配大量内存，模拟内存压力场景",
    "blade_cmd": f"{BLADE_BIN} create mem load --mode ram --mem-percent 60 --timeout 20",
    "witty_skills": ["offline-disk-fault-diagnosis", "linux-oom-analyzer"],
    "collect_cmds": {
        "dmesg.log": "dmesg",
        "meminfo.txt": "cat /proc/meminfo",
        "top.txt": "top -bn1",
        "top_mem_processes.txt": "ps aux --sort=-%mem",
        "free.txt": "free -h",
        "loadavg.txt": "cat /proc/loadavg",
        "vmstat_oom.txt": "cat /proc/vmstat | grep oom",
        "dmesg_oom.txt": "dmesg | grep -i 'oom\\|kill\\|out of memory'",
    },
    "diag_keywords": {"infocollect": ["memory", "mem", "oom"], "messages": ["oom|kill|memory|error"]},
}

SCENARIOS["network_delay"] = {
    "name": "网络延迟注入",
    "description": "通过 tc netem 在 eth0 上注入 500ms 网络延迟",
    "blade_cmd": "tc qdisc add dev eth0 root netem delay 500ms 50ms 25%; sleep 15; tc qdisc del dev eth0 root 2>/dev/null; echo NETEM_DONE",
    "witty_skills": ["offline-network-hardware-fault-diagnosis", "network-diagnosis"],
    "collect_cmds": {
        "dmesg.log": "dmesg", "top.txt": "top -bn1", "loadavg.txt": "cat /proc/loadavg",
        "ping_before.txt": "ping -c 3 -W 2 127.0.0.1",
        "ping_after.txt": "ping -c 3 -W 5 127.0.0.1",
        "tc_qdisc.txt": "tc qdisc show dev eth0 2>/dev/null || echo no_tc",
        "ss_summary.txt": "ss -s", "ifconfig.txt": "ip addr 2>/dev/null || ifconfig",
    },
    "diag_keywords": {"infocollect": ["network", "delay", "latency"], "messages": ["network|delay|eth0|error|timeout"]},
}

SCENARIOS["network_loss"] = {
    "name": "网络丢包注入",
    "description": "通过 tc netem 在 eth0 上注入 30% 网络丢包",
    "blade_cmd": "tc qdisc del dev eth0 root 2>/dev/null; tc qdisc add dev eth0 root netem loss 30%; sleep 15; tc qdisc del dev eth0 root 2>/dev/null; echo NETEM_DONE",
    "witty_skills": ["offline-network-hardware-fault-diagnosis", "network-diagnosis"],
    "collect_cmds": {
        "dmesg.log": "dmesg", "top.txt": "top -bn1", "loadavg.txt": "cat /proc/loadavg",
        "ping_before.txt": "ping -c 3 -W 2 127.0.0.1",
        "ping_after.txt": "ping -c 5 -W 5 127.0.0.1",
        "tc_qdisc.txt": "tc qdisc show dev eth0 2>/dev/null || echo no_tc",
        "ss_summary.txt": "ss -s", "ifconfig.txt": "ip addr 2>/dev/null || ifconfig",
    },
    "diag_keywords": {"infocollect": ["network", "loss", "packet"], "messages": ["network|loss|drop|eth0|error"]},
}

SCENARIOS["process_stop"] = {
    "name": "进程暂停注入",
    "description": "通过 ChaosBlade 暂停目标进程（SIGSTOP）",
    "blade_cmd": f"{BLADE_BIN} create process stop --process sleep",
    "witty_skills": ["system-resource-diagnosis", "offline-CPU-fault-diagnosis"],
    "collect_cmds": {
        "dmesg.log": "dmesg", "top.txt": "top -bn1", "loadavg.txt": "cat /proc/loadavg",
        "ps_before.txt": "ps aux | grep sleep | grep -v grep | head -10",
        "ps_state.txt": "ps aux | grep -E 'sleep|chaos_os' | grep -v grep | head -10",
    },
    "diag_keywords": {"infocollect": ["process", "sleep", "stop"], "messages": ["stopped|signal|SIGSTOP|process"]},
}

SCENARIOS["stress_ng"] = {
    "name": "stress-ng 全维度压力",
    "description": "通过 stress-ng 注入 CPU+IO+内存混合压力",
    "blade_cmd": "stress-ng --cpu 4 --io 2 --vm 1 --vm-bytes 512M --hdd 1 --timeout 15s 2>/dev/null; echo DONE",
    "witty_skills": ["online-cpu-scheduling-diagnosis", "offline-memory-fault-diagnosis"],
    "collect_cmds": {
        "dmesg.log": "dmesg", "top.txt": "top -bn1", "loadavg.txt": "cat /proc/loadavg",
        "cpu_stat.txt": "cat /proc/stat | head -n 17", "memory.txt": "free -h",
        "top_processes.txt": "ps aux --sort=-%cpu | head -10",
        "iostat.txt": "iostat -x 1 3 2>/dev/null || echo no_iostat",
        "uptime.txt": "uptime", "mpstat.txt": "mpstat -P ALL 1 1 2>/dev/null || echo no",
    },
    "diag_keywords": {"infocollect": ["CPU", "load", "memory", "stress"], "messages": ["stress|oom|load|CPU|error"]},
}

# ==================== 评测场景执行器 ====================
class ChaosWittyBench:
    def __init__(self, work_dir=WORK_DIR):
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)
        self.results = []
    
    def prepare_scenario(self, scenario_key):
        """在容器内准备场景前置条件"""
        s = SCENARIOS[scenario_key]
        if scenario_key == "process":
            # 启动一个持久进程作为 kill 目标
            docker_exec("kill $(ps aux | grep 'while true' | grep -v grep | awk '{print $2}') 2>/dev/null")
            docker_exec("nohup bash -c 'while true; do echo target > /dev/null; sleep 1; done' > /dev/null 2>&1 &")
            time.sleep(1)
            log("  已启动目标进程")

    def execute_scenario(self, scenario_key):
        """执行单个故障场景"""
        s = SCENARIOS[scenario_key]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        scene_dir = os.path.join(self.work_dir, f"{scenario_key}_{timestamp}")
        log_dir = os.path.join(scene_dir, "diagnosis")
        os.makedirs(os.path.join(log_dir, "messages"), exist_ok=True)
        os.makedirs(os.path.join(log_dir, "infocollect_logs"), exist_ok=True)

        log(f"\n{'='*55}")
        log(f"场景: {s['name']}")
        log(f"描述: {s['description']}")
        log(f"目录: {scene_dir}")
        log(f"{'='*55}")

        result = {
            "scenario": scenario_key,
            "name": s["name"],
            "time": timestamp,
            "dir": scene_dir,
            "inject_ok": False,
            "witty_ok": False,
            "inject_uid": "",
            "data_files": [],
        }

        # Step 1: 准备
        self.prepare_scenario(scenario_key)

        # Step 2: 采集基线
        log("\n[Step 1] 采集注入前基线...")
        baseline = docker_exec("cat /proc/loadavg; echo '==='; free -h; echo '==='; df -h /")
        with open(os.path.join(scene_dir, "baseline.txt"), "w") as f:
            f.write(baseline)

        # Step 3: 执行故障注入
        log(f"\n[Step 2] 执行故障注入...")
        log(f"  命令: {s['blade_cmd']}")
        inject_out = docker_exec(s["blade_cmd"])
        with open(os.path.join(scene_dir, "inject_result.txt"), "w") as f:
            f.write(inject_out)

        log(f"  返回: {inject_out[:120]}")
        m = re.search(r'"result":"([^"]+)"', inject_out)
        if m and '"code":200' in inject_out:
            result["inject_uid"] = m.group(1)
            result["inject_ok"] = True
            log(f"  ✅ 注入成功 (UID: {result['inject_uid']})")
        else:
            log(f"  ❌ 注入失败")

        # Step 4: 采集诊断日志（注入高峰期）
        log(f"\n[Step 3] 采集诊断日志...")
        time.sleep(3)
        container_dir = f"/tmp/bench_{scenario_key}"
        docker_exec(f"mkdir -p {container_dir}")

        for filename, cmd in s["collect_cmds"].items():
            docker_exec(f"{cmd} > {container_dir}/{filename} 2>/dev/null")

        # 等待注入完成（超时自动销毁）
        timeout = re.search(r'--timeout\s+(\d+)', s["blade_cmd"])
        wait_sec = int(timeout.group(1)) + 5 if timeout else 20
        log(f"  等待实验自动销毁 ({wait_sec}s)...")
        time.sleep(wait_sec)

        # 传输数据
        docker_cp(f"{container_dir}/.", os.path.join(log_dir, "infocollect_logs"))
        for fname in os.listdir(os.path.join(log_dir, "infocollect_logs")):
            fpath = os.path.join(log_dir, "infocollect_logs", fname)
            if fname == "dmesg.log":
                shutil.copy2(fpath, os.path.join(log_dir, "messages", fname))
            result["data_files"].append(fname)

        log(f"  采集了 {len(result['data_files'])} 个数据文件")

        # Step 5: witty 诊断分析
        log(f"\n[Step 4] witty 诊断分析...")

        # 全景扫描
        summary_out = run_cmd(f'python "{SUMMARY_PY}" "{log_dir}" -o')
        with open(os.path.join(scene_dir, "witty_summary.txt"), "w") as f:
            f.write(summary_out)

        # InfoCollect 分析
        kw = s["diag_keywords"].get("infocollect", [])
        if kw:
            kw_str = " ".join(f'"{k}"' for k in kw)
            ic_out = run_cmd(f'python "{INFOCOLLECT_PY}" "{os.path.join(log_dir, "infocollect_logs")}" -k {kw_str}')
        else:
            ic_out = run_cmd(f'python "{INFOCOLLECT_PY}" "{os.path.join(log_dir, "infocollect_logs")}" -o')
        with open(os.path.join(scene_dir, "witty_infocollect.txt"), "w") as f:
            f.write(ic_out)

        # Messages 分析
        kw2 = s["diag_keywords"].get("messages", [])
        if kw2:
            kw_str2 = " ".join(f'"{k}"' for k in kw2)
            msg_out = run_cmd(f'python "{MESSAGES_PY}" "{os.path.join(log_dir, "messages")}" -k {kw_str2}')
        else:
            msg_out = run_cmd(f'python "{MESSAGES_PY}" "{os.path.join(log_dir, "messages")}" -o')
        with open(os.path.join(scene_dir, "witty_messages.txt"), "w") as f:
            f.write(msg_out)

        result["witty_ok"] = True
        log(f"  ✅ witty 诊断完成")

        # Step 6: 提取关键指标
        log(f"\n[Step 5] 提取关键指标...")
        metrics = self.extract_metrics(scenario_key, scene_dir, log_dir)
        result["metrics"] = metrics
        log(f"  关键指标: {json.dumps(metrics, ensure_ascii=False)}")

        self.results.append(result)
        log(f"\n  ✅ 场景 '{scenario_key}' 完成\n")
        return result

    def extract_metrics(self, scenario_key, scene_dir, log_dir):
        """从采集的数据中提取关键指标"""
        metrics = {}
        ic_dir = os.path.join(log_dir, "infocollect_logs")

        # 通用: 提取 loadavg
        load_file = os.path.join(ic_dir, "loadavg.txt")
        if os.path.exists(load_file):
            with open(load_file) as f:
                content = f.read().strip()
            m = re.search(r'([\d.]+)\s+([\d.]+)\s+([\d.]+)', content)
            if m:
                metrics["load_1min"] = m.group(1)
                metrics["load_5min"] = m.group(2)
                metrics["load_15min"] = m.group(3)

        # 通用: 提取 top CPU
        top_file = os.path.join(ic_dir, "top.txt")
        if os.path.exists(top_file):
            with open(top_file) as f:
                top_text = f.read()
            m = re.search(r'%Cpu\(s\):\s+([\d.]+)\s+us', top_text)
            if m: metrics["cpu_us"] = m.group(1)
            m = re.search(r'([\d.]+)\s+id,', top_text)
            if m: metrics["cpu_idle"] = m.group(1)
            m = re.search(r'([\d.]+)\s+wa,', top_text)
            if m: metrics["cpu_iowait"] = m.group(1)

            # 提取 top 进程
            lines = top_text.strip().split("\n")
            for line in lines:
                if "chaos_os" in line or "dd" in line:
                    parts = line.split()
                    try:
                        pid_idx = next(i for i, p in enumerate(parts) if p.isdigit() and int(p) < 99999)
                        metrics["top_process"] = parts[-1]
                        metrics["top_process_cpu"] = parts[pid_idx + 1] if pid_idx + 1 < len(parts) else "N/A"
                    except:
                        pass
                    break

        # 场景特定
        if scenario_key == "disk_io":
            iostat_file = os.path.join(ic_dir, "iostat.txt")
            if os.path.exists(iostat_file):
                with open(iostat_file) as f:
                    for line in f:
                        m = re.search(r'(sd[a-z]+)\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)', line)
                        if m and float(m.group(2)) > 10:
                            metrics.setdefault("high_io_devices", []).append(f"{m.group(1)}: w/s={m.group(2)}, wkB/s={m.group(3)}")

        if scenario_key == "mem":
            mem_file = os.path.join(ic_dir, "meminfo.txt")
            if os.path.exists(mem_file):
                with open(mem_file) as f:
                    for line in f:
                        m = re.search(r'MemTotal:\s+(\d+)', line)
                        if m: metrics["mem_total_kb"] = m.group(1)
                        m = re.search(r'MemFree:\s+(\d+)', line)
                        if m: metrics["mem_free_kb"] = m.group(1)
                        m = re.search(r'MemAvailable:\s+(\d+)', line)
                        if m: metrics["mem_avail_kb"] = m.group(1)
                        m = re.search(r'AnonPages:\s+(\d+)', line)
                        if m: metrics["anon_pages_kb"] = m.group(1)

        if scenario_key == "disk_fill":
            df_file = os.path.join(ic_dir, "df.txt")
            if os.path.exists(df_file):
                with open(df_file) as f:
                    for line in f:
                        m = re.search(r'(\d+)%\s+/(\s|$)', line)
                        if m: metrics["disk_use_pct"] = m.group(1)

        if scenario_key == "process":
            ps_before = os.path.join(ic_dir, "ps_before.txt")
            ps_after = os.path.join(ic_dir, "ps_after.txt")
            metrics["target_exists_before"] = os.path.exists(ps_before) and os.path.getsize(ps_before) > 0

        return metrics

    def run_all(self, scenarios=None):
        """运行所有或指定场景"""
        if scenarios is None:
            scenarios = list(SCENARIOS.keys())

        log("=" * 55)
        log("ChaosBlade + witty 自动化评测框架启动")
        log(f"共 {len(scenarios)} 个场景: {', '.join(scenarios)}")
        log("=" * 55)

        for key in scenarios:
            if key not in SCENARIOS:
                log(f"⚠️ 未知场景: {key}，跳过")
                continue
            self.execute_scenario(key)

        self.generate_summary_report()
        log("\n" + "=" * 55)
        log(f"全部 {len(self.results)}/{len(scenarios)} 个场景完成")
        log("=" * 55)
        return self.results

    def generate_summary_report(self):
        """生成汇总评测报告"""
        report_path = os.path.join(self.work_dir, "bench_summary_report.md")
        lines = []
        lines.append("# ChaosBlade + witty 自动化评测报告\n")
        lines.append(f"> **评测时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> **总场景数**: {len(self.results)}\n")
        lines.append("## 总体结果\n")
        lines.append("| 场景 | 故障类型 | 注入状态 | witty 诊断 | 注入 UID |")
        lines.append("|------|----------|----------|-----------|----------|")
        for r in self.results:
            inj = "✅" if r["inject_ok"] else "❌"
            wit = "✅" if r["witty_ok"] else "❌"
            lines.append(f"| {r['scenario']} | {r['name']} | {inj} | {wit} | {r['inject_uid'][:16] if r['inject_uid'] else 'N/A'} |")

        lines.append("\n## 场景详情\n")
        for r in self.results:
            lines.append(f"### {r['scenario']}: {r['name']}\n")
            lines.append(f"**注入命令**: `{SCENARIOS[r['scenario']]['blade_cmd']}`\n")
            lines.append(f"**注入状态**: {'✅ 成功' if r['inject_ok'] else '❌ 失败'}\n")
            lines.append(f"**实验 UID**: `{r['inject_uid'] or 'N/A'}`\n")
            lines.append(f"**诊断状态**: {'✅ 完成' if r['witty_ok'] else '❌ 失败'}\n")
            lines.append(f"**数据文件**: {', '.join(r['data_files'][:10])}\n")
            if r.get("metrics"):
                lines.append("**关键指标**:\n")
                lines.append("| 指标 | 值 |")
                lines.append("|------|-----|")
                for k, v in r["metrics"].items():
                    if isinstance(v, list):
                        for i, item in enumerate(v):
                            lines.append(f"| {k}[{i}] | {item} |")
                    else:
                        lines.append(f"| {k} | {v} |")
            lines.append("---\n")

        lines.append("\n## 系统环境\n")
        lines.append(f"| 项目 | 内容 |")
        lines.append(f"|------|------|")
        env = docker_exec("cat /proc/loadavg; echo '==='; free -h | head -2; echo '==='; nproc; echo '==='; uname -r; echo '==='; cat /etc/os-release | grep PRETTY_NAME")
        for line in env.split("\n"):
            if "PRETTY_NAME" in line:
                lines.append(f"| OS | {line.split('=')[1].strip().strip('\"')} |")
        lines.append(f"| 内核 | {docker_exec('uname -r').strip()} |")
        lines.append(f"| CPU | {docker_exec('nproc').strip()} 核 |")
        lines.append(f"| 内存 | {docker_exec('free -h | grep Mem | head -1 | awk \'{print $2}\'').strip()} |")
        lines.append(f"| ChaosBlade | v1.8.0 |")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        log(f"\n📄 评测报告已生成: {report_path}")
        return report_path


# ==================== 主入口 ====================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ChaosBlade + witty 自动化评测框架")
    parser.add_argument("--scenario", "-s", help="指定运行单个场景")
    parser.add_argument("--list", "-l", action="store_true", help="列出可用场景")
    parser.add_argument("--output", "-o", default=WORK_DIR, help="输出目录")
    args = parser.parse_args()

    if args.list:
        print("\n可用场景:\n")
        for k, v in SCENARIOS.items():
            print(f"  {k:12s}  {v['name']}")
            print(f"  {'':12s}  {v['description']}")
            print(f"  {'':12s}  命令: {v['blade_cmd']}")
            print()
        sys.exit(0)

    bench = ChaosWittyBench(work_dir=args.output)

    if args.scenario:
        bench.run_all([args.scenario])
    else:
        bench.run_all()
