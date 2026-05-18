#!/usr/bin/env python3
"""
ChaosBlade + witty Auto Benchmark - One-click Entry
===================================================
3 steps: 1.Check env -> 2.Select scenario -> 3.View report

Usage:
  python run.py              Interactive menu
  python run.py --all        Run all 5 scenarios
  python run.py cpu          Run CPU scenario
  python run.py --list       List scenarios
"""

import os, sys, subprocess, time, re, io
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK = os.path.join(ROOT, "scripts", "chaos_witty_agent_skill.py")
CONTAINER = "chaosblade-demo"

SCENARIOS = {
    "1":  ("cpu",           "CPU overload 70% (20s)"),
    "2":  ("disk_io",       "Disk I/O write 50MB (15s)"),
    "3":  ("process",       "Process kill SIGTERM"),
    "4":  ("disk_fill",     "Disk fill 80% (15s)"),
    "5":  ("mem",           "Memory load 60% (20s)"),
    "6":  ("network_delay", "Network delay 3000ms (20s)"),
    "7":  ("network_loss",  "Network packet loss 50% (20s)"),
    "8":  ("process_stop",  "Process stop (pause) SIGSTOP"),
    "9":  ("stress_ng",     "stress-ng CPU+IO+memory mixed (15s)"),
}

def section(title):
    print("\n" + "=" * 55)
    print("  " + title)
    print("=" * 55)

def check_env():
    section("[1/3] Environment Check")

    # Docker
    r = subprocess.run(f"docker ps --filter name={CONTAINER} --format '{{.Status}}'",
                       shell=True, capture_output=True, text=True, timeout=10)
    if "Up" in r.stdout or "Up" in r.stderr:
        print("  [OK] Docker container running")
    else:
        print("  [..] Starting container...")
        subprocess.run(f"docker start {CONTAINER}", shell=True, capture_output=True, timeout=10)
        time.sleep(3)

    # ChaosBlade
    r = subprocess.run(
        f"docker exec {CONTAINER} bash -c \"cd /opt/chaosblade-1.8.0 && ./blade version\"",
        shell=True, capture_output=True, text=True, timeout=10)
    combined = r.stdout + r.stderr
    if "Version:" in combined and "1.8.0" in combined:
        print("  [OK] ChaosBlade v1.8.0")
    else:
        print("  [ERROR] ChaosBlade unavailable: " + r.stdout[:100])
        return False

    # witty scripts
    skill = r"C:\Users\86188\.config\opencode\skills\offline-disk-fault-diagnosis\scripts"
    summary = os.path.join(skill, "diagnose_summary.py")
    if os.path.exists(summary):
        print("  [OK] witty diagnosis scripts")
    else:
        print("  [ERROR] witty scripts not found: " + summary)
        return False

    r = subprocess.run("python --version", shell=True, capture_output=True, text=True, timeout=5)
    print(f"  [OK] {r.stdout.strip()}")

    print("\n  Environment ready!\n")
    return True

def select_scenario(preset=""):
    if preset == "--list":
        subprocess.run(f"python {FRAMEWORK} --list", shell=True)
        return ""
    if preset == "--all":
        return "all"
    if preset:
        return preset

    section("[2/3] Select Fault Scenario")

    for k, (s, d) in SCENARIOS.items():
        print(f"  [{k}] {d}")
    print("  [A] Run all 9 scenarios")
    print("  [L] List scenarios/agents")
    print("  [Q] Quit")

    try:
        choice = input("\nChoice (1-9, A=all, L=list, Q=quit): ").upper()
    except EOFError:
        choice = "Q"

    if choice == "Q": return "quit"
    if choice == "L":
        subprocess.run(f"python {FRAMEWORK} --list", shell=True)
        return ""
    if choice == "A": return "all"
    if choice in SCENARIOS: return SCENARIOS[choice][0]
    print("  Invalid choice")
    return ""

def run_bench(scenario):
    if not scenario: return
    section("[3/3] Running Benchmark")

    if scenario == "all":
        print("  Running all 5 scenarios (~3 min)...\n")
        r = subprocess.run(f"python \"{FRAMEWORK}\"", shell=True, timeout=300)
    else:
        name = next((d for k, (s, d) in SCENARIOS.items() if s == scenario), scenario)
        print(f"  Running: {name}\n")
        r = subprocess.run(f"python \"{FRAMEWORK}\" -s {scenario}", shell=True, timeout=120)

    if r.returncode == 0:
        print("\n  [OK] Benchmark complete!")
        show_report()
    else:
        print("\n  [ERROR] Benchmark failed")

def show_report():
    section("View Report")

    report_dir = os.path.join(ROOT, "bench_output")
    reports = []

    summary = os.path.join(report_dir, "chaos_witty_agent_skill_report.md")
    if os.path.exists(summary):
        reports.append(("Summary Report (all scenarios)", summary))

    if os.path.isdir(report_dir):
        dirs = [d for d in os.listdir(report_dir) if os.path.isdir(os.path.join(report_dir, d))
                and re.match(r"^(cpu|disk_io|process|disk_fill|mem)_\d{14}$", d)]
        dirs.sort(reverse=True)
        for d in dirs[:5]:
            rca = os.path.join(report_dir, d, "baize_rca_report.md")
            if os.path.exists(rca):
                name = re.sub(r"_\d{14}$", "", d)
                reports.append((f"{name} RCA Report", rca))

    for i, (name, path) in enumerate(reports, 1):
        print(f"  [{i}] {name}")
        print(f"       {path}")

    if not reports:
        print("  No reports yet")
        return

    try:
        choice = input("\nEnter number to view (Enter to skip): ")
    except EOFError:
        return

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(reports):
            with open(reports[idx][1], encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            print(f"\n--- {reports[idx][0]} ---")
            for line in lines[:50]:
                print(line)
            if len(lines) > 50:
                print(f"\n... ({len(lines)} lines total, showing first 50)")

def show_help():
    print("=" * 55)
    print("  ChaosBlade + witty Auto Benchmark Tool")
    print("=" * 55)
    print()
    print("  3 steps: Check env -> Select scenario -> View report")
    print()
    print("  Available scenarios:")
    for k, (s, d) in SCENARIOS.items():
        print(f"    [{k}] {d}")
    print()
    print("  Quick commands:")
    print("    python run.py --all    Run all 5 scenarios (~3 min)")
    print("    python run.py cpu      Run CPU scenario")
    print("    python run.py --list   List scenarios")
    print("    python run.py          Interactive menu")
    print()

if __name__ == "__main__":
    show_help()

    preset = ""
    if len(sys.argv) > 1:
        preset = sys.argv[1]
    if preset == "--help" or preset == "-h":
        show_help()
        sys.exit(0)

    if not check_env():
        print("\nEnvironment check failed. Fix and retry.")
        sys.exit(1)

    scenario = select_scenario(preset)
    while scenario == "":
        scenario = select_scenario()

    if scenario and scenario != "quit":
        run_bench(scenario)

    try:
        input("\nPress Enter to exit...")
    except EOFError:
        pass
