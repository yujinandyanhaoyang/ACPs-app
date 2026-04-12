from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = PROJECT_ROOT / "artifacts" / "safe_pressure_test_report.md"
DEFAULT_WORKDIR = PROJECT_ROOT / "artifacts" / "safe_pressure_test_runs"
PAGE_SIZE = 4096
SECTOR_SIZE = 512


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _run_cmd(args: Sequence[str]) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=True)
    except Exception:
        return ""
    return proc.stdout.strip()


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "n/a"


def _fmt_float(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "n/a"


def _fmt_pct(value: Any, digits: int = 1) -> str:
    return f"{_fmt_float(value, digits)}%"


def _fmt_mib(value: Any, digits: int = 1) -> str:
    return f"{_fmt_float(value, digits)} MiB"


def _fmt_gib(value: Any, digits: int = 2) -> str:
    try:
        return f"{_safe_bytes_to_gib(int(value)):.{digits}f} GiB"
    except Exception:
        return "n/a"


def _parse_csv_ints(raw: str) -> List[int]:
    values: List[int] = []
    for part in (raw or "").split(","):
        text = part.strip()
        if not text:
            continue
        values.append(int(text))
    return values


def _parse_csv_floats(raw: str) -> List[float]:
    values: List[float] = []
    for part in (raw or "").split(","):
        text = part.strip()
        if not text:
            continue
        values.append(float(text))
    return values


def _read_meminfo() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for line in _read_text(Path("/proc/meminfo")).splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        fields = rest.strip().split()
        if not fields:
            continue
        try:
            out[key] = int(fields[0])
        except Exception:
            continue
    return out


def _read_loadavg() -> float:
    try:
        return float(_read_text(Path("/proc/loadavg")).split()[0])
    except Exception:
        return 0.0


def _read_pressure(path: Path) -> Dict[str, float]:
    data: Dict[str, float] = {}
    try:
        for token in _read_text(path).replace("\n", " ").split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            try:
                data[key] = float(value)
            except Exception:
                continue
    except Exception:
        pass
    return data


def _read_proc_stat() -> Dict[str, int]:
    first = _read_text(Path("/proc/stat")).splitlines()[0].split()
    values = [int(item) for item in first[1:]]
    while len(values) < 10:
        values.append(0)
    user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice = values[:10]
    total = sum(values[:10])
    idle_all = idle + iowait
    return {
        "total": total,
        "idle": idle_all,
        "iowait": iowait,
    }


def _read_diskstats(device: str) -> Dict[str, int]:
    for line in _read_text(Path("/proc/diskstats")).splitlines():
        fields = line.split()
        if len(fields) < 14:
            continue
        if fields[2] != device:
            continue
        return {
            "reads_completed": int(fields[3]),
            "reads_merged": int(fields[4]),
            "sectors_read": int(fields[5]),
            "time_reading_ms": int(fields[6]),
            "writes_completed": int(fields[7]),
            "writes_merged": int(fields[8]),
            "sectors_written": int(fields[9]),
            "time_writing_ms": int(fields[10]),
            "ios_in_progress": int(fields[11]),
            "time_doing_io_ms": int(fields[12]),
            "weighted_time_doing_io_ms": int(fields[13]),
        }
    return {}


def _root_source() -> str:
    out = _run_cmd(["findmnt", "-n", "-o", "SOURCE", "--target", "/"])
    if out:
        return out
    for line in _read_text(Path("/proc/self/mountinfo")).splitlines():
        parts = line.split()
        if len(parts) < 10:
            continue
        mount_point = parts[4]
        if mount_point == "/":
            return parts[9]
    return ""


def _root_fs_type() -> str:
    out = _run_cmd(["findmnt", "-n", "-o", "FSTYPE", "--target", "/"])
    if out:
        return out
    return ""


def _root_free_bytes() -> int:
    st = os.statvfs("/")
    return st.f_bavail * st.f_frsize


def _root_device_name() -> str:
    source = _root_source()
    if not source:
        return ""
    base = os.path.basename(source)
    if base.startswith("mapper/"):
        return base.split("/", 1)[-1]
    if base.startswith("dm-"):
        return base
    if base.startswith("loop"):
        return base
    if source.startswith("/dev/"):
        pkname = _run_cmd(["lsblk", "-no", "PKNAME", source]).strip()
        if pkname:
            return pkname
        return os.path.basename(source)
    return base


def _cgroup_dir() -> Path:
    try:
        cgroup_line = _read_text(Path("/proc/self/cgroup")).splitlines()[0]
        _, _, rel = cgroup_line.partition("::")
        rel = rel.strip()
        if rel:
            return Path("/sys/fs/cgroup") / rel.lstrip("/")
    except Exception:
        pass
    return Path("/sys/fs/cgroup")


def _read_cgroup_values(cgroup_dir: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for name in ("cpu.max", "cpu.weight", "memory.max", "memory.high", "memory.swap.max", "pids.max"):
        path = cgroup_dir / name
        if path.exists():
            values[name] = _read_text(path)
    return values


def _safe_mib_to_bytes(mib: float) -> int:
    return max(1, int(mib * 1024 * 1024))


def _safe_bytes_to_mib(value: int) -> float:
    return value / (1024 * 1024)


def _safe_bytes_to_gib(value: int) -> float:
    return value / (1024 * 1024 * 1024)


@dataclass
class Sample:
    ts: float
    load1: float
    cpu_pct: float
    iowait_pct: float
    mem_avail_mib: float
    mem_used_mib: float
    io_util_pct: float
    io_await_ms: float
    io_throughput_mib_s: float
    psi_cpu_some: float
    psi_cpu_full: float
    psi_mem_some: float
    psi_mem_full: float
    psi_io_some: float
    psi_io_full: float


@dataclass
class StepResult:
    phase: str
    step: int
    target_label: str
    duration_s: float
    stable: bool
    stop_reason: str
    samples: List[Sample] = field(default_factory=list)
    peak_cpu_pct: float = 0.0
    peak_iowait_pct: float = 0.0
    peak_io_util_pct: float = 0.0
    peak_io_await_ms: float = 0.0
    min_mem_avail_mib: float = 0.0
    avg_mem_avail_mib: float = 0.0
    avg_cpu_pct: float = 0.0
    avg_load_ratio: float = 0.0
    peak_psi_cpu_some: float = 0.0
    peak_psi_mem_some: float = 0.0
    peak_psi_io_some: float = 0.0


@dataclass
class PhaseSummary:
    name: str
    unit: str
    results: List[StepResult]
    highest_stable: Optional[StepResult]
    stop_reason: str


def _compute_sample(
    prev_cpu: Dict[str, int],
    prev_disk: Dict[str, int],
    prev_wall: float,
    root_device: str,
    cpu_count: int,
) -> Tuple[Sample, Dict[str, int], Dict[str, int], float]:
    now_wall = time.perf_counter()
    now_cpu = _read_proc_stat()
    now_disk = _read_diskstats(root_device)
    mem = _read_meminfo()
    pressure_cpu = _read_pressure(Path("/proc/pressure/cpu"))
    pressure_mem = _read_pressure(Path("/proc/pressure/memory"))
    pressure_io = _read_pressure(Path("/proc/pressure/io"))
    load1 = _read_loadavg()

    cpu_delta = max(now_cpu["total"] - prev_cpu.get("total", now_cpu["total"]), 1)
    idle_delta = max(now_cpu["idle"] - prev_cpu.get("idle", now_cpu["idle"]), 0)
    iowait_delta = max(now_cpu["iowait"] - prev_cpu.get("iowait", now_cpu["iowait"]), 0)
    cpu_pct = max(0.0, min(100.0, 100.0 * (cpu_delta - idle_delta) / cpu_delta))
    iowait_pct = max(0.0, min(100.0, 100.0 * iowait_delta / cpu_delta))

    mem_total_kib = mem.get("MemTotal", 0)
    mem_avail_kib = mem.get("MemAvailable", 0)
    mem_used_mib = _safe_bytes_to_mib(max((mem_total_kib - mem_avail_kib), 0) * 1024)
    mem_avail_mib = _safe_bytes_to_mib(mem_avail_kib * 1024)

    elapsed_ms = max((now_wall - prev_wall) * 1000.0, 1.0)
    io_util_pct = 0.0
    io_await_ms = 0.0
    io_throughput_mib_s = 0.0
    if prev_disk and now_disk:
        reads_delta = max(now_disk["reads_completed"] - prev_disk.get("reads_completed", now_disk["reads_completed"]), 0)
        writes_delta = max(now_disk["writes_completed"] - prev_disk.get("writes_completed", now_disk["writes_completed"]), 0)
        read_time_delta = max(now_disk["time_reading_ms"] - prev_disk.get("time_reading_ms", now_disk["time_reading_ms"]), 0)
        write_time_delta = max(now_disk["time_writing_ms"] - prev_disk.get("time_writing_ms", now_disk["time_writing_ms"]), 0)
        io_time_delta = max(now_disk["time_doing_io_ms"] - prev_disk.get("time_doing_io_ms", now_disk["time_doing_io_ms"]), 0)
        sectors_delta = max(now_disk["sectors_read"] - prev_disk.get("sectors_read", now_disk["sectors_read"]), 0) + max(
            now_disk["sectors_written"] - prev_disk.get("sectors_written", now_disk["sectors_written"]), 0
        )
        io_util_pct = max(0.0, min(100.0, 100.0 * io_time_delta / elapsed_ms))
        ops = reads_delta + writes_delta
        if ops > 0:
            io_await_ms = (read_time_delta + write_time_delta) / ops
        io_throughput_mib_s = ((sectors_delta * SECTOR_SIZE) / (1024 * 1024)) / max(elapsed_ms / 1000.0, 1e-6)

    sample = Sample(
        ts=time.time(),
        load1=load1,
        cpu_pct=cpu_pct,
        iowait_pct=iowait_pct,
        mem_avail_mib=mem_avail_mib,
        mem_used_mib=mem_used_mib,
        io_util_pct=io_util_pct,
        io_await_ms=io_await_ms,
        io_throughput_mib_s=io_throughput_mib_s,
        psi_cpu_some=pressure_cpu.get("avg10", 0.0),
        psi_cpu_full=pressure_cpu.get("full", 0.0),
        psi_mem_some=pressure_mem.get("avg10", 0.0),
        psi_mem_full=pressure_mem.get("full", 0.0),
        psi_io_some=pressure_io.get("avg10", 0.0),
        psi_io_full=pressure_io.get("full", 0.0),
    )
    return sample, now_cpu, now_disk, now_wall


def _cpu_worker(stop_event: mp.Event) -> None:
    value = 0
    while not stop_event.is_set():
        value = (value * 1664525 + 1013904223) & 0xFFFFFFFF
        value ^= (value << 13) & 0xFFFFFFFF
        value ^= (value >> 17)
        value ^= (value << 5) & 0xFFFFFFFF


def _memory_worker(stop_event: mp.Event, target_mib: int) -> None:
    blocks: List[bytearray] = []
    remaining = _safe_mib_to_bytes(float(target_mib))
    chunk = 16 * 1024 * 1024
    try:
        while remaining > 0 and not stop_event.is_set():
            size = min(chunk, remaining)
            block = bytearray(size)
            for offset in range(0, size, PAGE_SIZE):
                block[offset] = (offset // PAGE_SIZE) & 0xFF
            blocks.append(block)
            remaining -= size
        while not stop_event.is_set():
            time.sleep(0.2)
    finally:
        blocks.clear()


def _disk_worker(stop_event: mp.Event, file_path: str, target_mib: int) -> None:
    path = Path(file_path)
    block_size = 4 * 1024 * 1024
    total_size = _safe_mib_to_bytes(float(target_mib))
    payload = bytearray(block_size)
    for i in range(0, block_size, PAGE_SIZE):
        payload[i] = (i // PAGE_SIZE) & 0xFF
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(total_size)
    try:
        with path.open("r+b", buffering=0) as f:
            while not stop_event.is_set():
                written = 0
                while written < total_size and not stop_event.is_set():
                    size = min(block_size, total_size - written)
                    if size != len(payload):
                        chunk = bytes(payload[:size])
                    else:
                        chunk = payload
                    f.write(chunk)
                    written += size
                    if written % (16 * 1024 * 1024) == 0:
                        f.flush()
                        os.fsync(f.fileno())
                f.flush()
                os.fsync(f.fileno())
                f.seek(0)
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _collect_phase_metrics(samples: List[Sample], phase: str, step: int, target_label: str, duration_s: float, stable: bool, stop_reason: str) -> StepResult:
    if samples:
        peak_cpu_pct = max(s.cpu_pct for s in samples)
        peak_iowait_pct = max(s.iowait_pct for s in samples)
        peak_io_util_pct = max(s.io_util_pct for s in samples)
        peak_io_await_ms = max(s.io_await_ms for s in samples)
        min_mem_avail_mib = min(s.mem_avail_mib for s in samples)
        avg_mem_avail_mib = sum(s.mem_avail_mib for s in samples) / len(samples)
        avg_cpu_pct = sum(s.cpu_pct for s in samples) / len(samples)
        avg_load_ratio = sum(s.load1 for s in samples) / len(samples)
        cpu_count = max(os.cpu_count() or 1, 1)
        avg_load_ratio /= cpu_count
        peak_psi_cpu_some = max(s.psi_cpu_some for s in samples)
        peak_psi_mem_some = max(s.psi_mem_some for s in samples)
        peak_psi_io_some = max(s.psi_io_some for s in samples)
    else:
        peak_cpu_pct = peak_iowait_pct = peak_io_util_pct = peak_io_await_ms = 0.0
        min_mem_avail_mib = avg_mem_avail_mib = avg_cpu_pct = avg_load_ratio = 0.0
        peak_psi_cpu_some = peak_psi_mem_some = peak_psi_io_some = 0.0
    return StepResult(
        phase=phase,
        step=step,
        target_label=target_label,
        duration_s=duration_s,
        stable=stable,
        stop_reason=stop_reason,
        samples=samples,
        peak_cpu_pct=peak_cpu_pct,
        peak_iowait_pct=peak_iowait_pct,
        peak_io_util_pct=peak_io_util_pct,
        peak_io_await_ms=peak_io_await_ms,
        min_mem_avail_mib=min_mem_avail_mib,
        avg_mem_avail_mib=avg_mem_avail_mib,
        avg_cpu_pct=avg_cpu_pct,
        avg_load_ratio=avg_load_ratio,
        peak_psi_cpu_some=peak_psi_cpu_some,
        peak_psi_mem_some=peak_psi_mem_some,
        peak_psi_io_some=peak_psi_io_some,
    )


def _run_phase(
    *,
    phase: str,
    steps: Sequence[Tuple[int, str]],
    baseline_cpu: Dict[str, int],
    baseline_disk: Dict[str, int],
    baseline_iowait_pct: float,
    baseline_io_util_pct: float,
    root_device: str,
    cpu_count: int,
    baseline_mem_avail_mib: float,
    stop_event: mp.Event,
    step_seconds: int,
    cooldown_seconds: int,
    workdir: Path,
    memory_reserve_mib: int,
    disk_file_mib: int,
) -> PhaseSummary:
    results: List[StepResult] = []
    highest_stable: Optional[StepResult] = None
    stop_reason = "completed"
    ctx = mp.get_context("spawn")

    for step_value, label in steps:
        if stop_event.is_set():
            stop_reason = "interrupted"
            break

        worker_stop = ctx.Event()
        workers: List[mp.Process] = []

        if phase == "cpu":
            for _ in range(step_value):
                proc = ctx.Process(target=_cpu_worker, args=(worker_stop,))
                proc.start()
                workers.append(proc)
        elif phase == "memory":
            for _ in range(1):
                proc = ctx.Process(target=_memory_worker, args=(worker_stop, step_value))
                proc.start()
                workers.append(proc)
        elif phase == "disk":
            for idx in range(step_value):
                path = workdir / f"disk_{phase}_{step_value}_{idx}.bin"
                proc = ctx.Process(target=_disk_worker, args=(worker_stop, str(path), disk_file_mib))
                proc.start()
                workers.append(proc)
        else:
            raise ValueError(f"unknown phase: {phase}")

        samples: List[Sample] = []
        stable = True
        local_reason = "completed"
        prev_cpu = dict(baseline_cpu)
        prev_disk = dict(baseline_disk)
        prev_wall = time.perf_counter()
        started = time.perf_counter()
        deadline = started + step_seconds
        sample_count = 0

        while time.perf_counter() < deadline and not stop_event.is_set():
            sample, prev_cpu, prev_disk, prev_wall = _compute_sample(prev_cpu, prev_disk, prev_wall, root_device, cpu_count)
            samples.append(sample)
            sample_count += 1

            cpu_killed = any(not p.is_alive() and p.exitcode not in (0, None) for p in workers)
            if cpu_killed:
                stable = False
                local_reason = "worker_exit"
                stop_event.set()
                break

            if phase == "cpu":
                if sample.iowait_pct > max(20.0, baseline_iowait_pct + 15.0) or sample.psi_cpu_some > 50.0 or sample.load1 > cpu_count * 1.8:
                    stable = False
                    local_reason = "safety_threshold"
                    break
            elif phase == "memory":
                if sample.mem_avail_mib < memory_reserve_mib or sample.psi_mem_some > 20.0:
                    stable = False
                    local_reason = "safety_threshold"
                    break
            elif phase == "disk":
                if sample.io_util_pct > max(90.0, baseline_io_util_pct + 50.0) or sample.io_await_ms > 50.0 or sample.iowait_pct > max(25.0, baseline_iowait_pct + 20.0) or sample.psi_io_some > 20.0:
                    stable = False
                    local_reason = "safety_threshold"
                    break

            time.sleep(1.0)

        duration_s = time.perf_counter() - started

        worker_stop.set()
        for proc in workers:
            proc.join(timeout=10)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)

        if phase == "memory":
            stop_point = _fmt_mib(step_value)
        else:
            stop_point = label
        result = _collect_phase_metrics(samples, phase, step_value, stop_point, duration_s, stable, local_reason)
        results.append(result)
        if stable:
            highest_stable = result
        else:
            stop_reason = local_reason
            break

        if cooldown_seconds > 0:
            end = time.perf_counter() + cooldown_seconds
            while time.perf_counter() < end and not stop_event.is_set():
                time.sleep(0.5)

    return PhaseSummary(name=phase, unit="workers" if phase != "memory" else "MiB", results=results, highest_stable=highest_stable, stop_reason=stop_reason)


def _build_steps(args: argparse.Namespace, total_mem_mib: float) -> Dict[str, List[Tuple[int, str]]]:
    cpu_count = max(os.cpu_count() or 1, 1)
    cpu_steps = args.cpu_workers
    if cpu_steps:
        cpu_values = [max(1, min(cpu_count, value)) for value in cpu_steps]
    else:
        cpu_values = sorted({max(1, cpu_count // 4), max(1, cpu_count // 2), max(1, (cpu_count * 3) // 4), cpu_count})
    cpu_steps_out = [(value, f"{value} workers") for value in cpu_values]

    mem_cap_mib = max(256.0, total_mem_mib - float(args.memory_reserve_mib))
    mem_fractions = args.memory_fractions or [0.25, 0.40, 0.55, 0.70, 0.80]
    mem_values: List[int] = []
    for frac in mem_fractions:
        value = int(mem_cap_mib * frac)
        value = max(256, min(int(mem_cap_mib), (value // 256) * 256))
        if value > 0:
            mem_values.append(value)
    mem_values = sorted(dict.fromkeys(mem_values))
    mem_steps_out = [(value, _fmt_mib(value)) for value in mem_values]

    disk_steps = args.disk_workers or [1, 2, 4]
    disk_values = sorted({max(1, value) for value in disk_steps})
    disk_steps_out = [(value, f"{value} workers") for value in disk_values]

    return {"cpu": cpu_steps_out, "memory": mem_steps_out, "disk": disk_steps_out}


def _pick_highest_stable(phase: PhaseSummary) -> Optional[StepResult]:
    if phase.highest_stable is not None:
        return phase.highest_stable
    stable = [result for result in phase.results if result.stable]
    return stable[-1] if stable else None


def _make_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Safe Pressure Test Report")
    lines.append("")
    system = report["system"]
    config = report["config"]
    summary = report["summary"]
    baseline = report.get("baseline") or {}
    lines.append("## System")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at']}`")
    lines.append(f"- Host: `{system['hostname']}`")
    lines.append(f"- Kernel: `{system['kernel']}`")
    lines.append(f"- CPU: `{system['cpu_count']}` logical CPUs")
    lines.append(f"- Total memory: `{_fmt_gib(system['mem_total_bytes'])}`")
    lines.append(f"- MemAvailable at start: `{_fmt_gib(system['mem_available_bytes'])}`")
    lines.append(f"- Root source: `{system['root_source']}`")
    lines.append(f"- Root fs type: `{system['root_fs']}`")
    lines.append(f"- Root free space: `{_fmt_gib(system['root_free_bytes'])}`")
    lines.append(f"- Cgroup path: `{system['cgroup_dir']}`")
    lines.append(f"- Cgroup cpu.max: `{system['cgroup'].get('cpu.max', 'n/a')}`")
    lines.append(f"- Cgroup memory.max: `{system['cgroup'].get('memory.max', 'n/a')}`")
    lines.append(f"- Cgroup memory.swap.max: `{system['cgroup'].get('memory.swap.max', 'n/a')}`")
    lines.append("")
    if baseline:
        lines.append("## Baseline")
        lines.append("")
        lines.append(f"- Duration: `{_fmt_float(baseline.get('duration_s', 0.0))}s`")
        lines.append(f"- Avg CPU: `{_fmt_pct(baseline.get('avg_cpu_pct', 0.0))}`")
        lines.append(f"- Peak CPU: `{_fmt_pct(baseline.get('peak_cpu_pct', 0.0))}`")
        lines.append(f"- Avg iowait: `{_fmt_pct(baseline.get('avg_iowait_pct', 0.0))}`")
        lines.append(f"- Peak iowait: `{_fmt_pct(baseline.get('peak_iowait_pct', 0.0))}`")
        lines.append(f"- Avg MemAvailable: `{_fmt_mib(baseline.get('avg_mem_avail_mib', 0.0))}`")
        lines.append(f"- Min MemAvailable: `{_fmt_mib(baseline.get('min_mem_avail_mib', 0.0))}`")
        lines.append(f"- Peak IO util: `{_fmt_pct(baseline.get('peak_io_util_pct', 0.0))}`")
        lines.append(f"- Peak PSI cpu avg10: `{_fmt_float(baseline.get('peak_psi_cpu_some', 0.0))}`")
        lines.append(f"- Peak PSI mem avg10: `{_fmt_float(baseline.get('peak_psi_mem_some', 0.0))}`")
        lines.append(f"- Peak PSI io avg10: `{_fmt_float(baseline.get('peak_psi_io_some', 0.0))}`")
        lines.append("")
    lines.append("## Configuration")
    lines.append("")
    lines.append(f"- Baseline seconds: `{config['baseline_seconds']}`")
    lines.append(f"- Step seconds: `{config['step_seconds']}`")
    lines.append(f"- Cooldown seconds: `{config['cooldown_seconds']}`")
    lines.append(f"- Memory reserve: `{_fmt_mib(config['memory_reserve_mib'])}`")
    lines.append(f"- Disk file size per worker: `{_fmt_mib(config['disk_file_mib'])}`")
    lines.append(f"- CPU steps: `{', '.join(str(x) for x in config['cpu_steps'])}`")
    lines.append(f"- Memory steps: `{', '.join(_fmt_mib(x) for x in config['memory_steps'])}`")
    lines.append(f"- Disk steps: `{', '.join(str(x) for x in config['disk_steps'])}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Phase | Highest stable step | Stop reason | Peak CPU | Peak iowait | Peak PSI avg10 | Peak IO util |")
    lines.append("|---|---:|---|---:|---:|---:|---:|")
    for phase_name in ("cpu", "memory", "disk"):
        phase = summary[phase_name]
        highest = phase["highest_stable"]
        stable_label = highest["target_label"] if highest else "n/a"
        if phase_name == "cpu":
            psi_peak = phase["peak_psi_cpu_some"]
        elif phase_name == "memory":
            psi_peak = phase["peak_psi_mem_some"]
        else:
            psi_peak = phase["peak_psi_io_some"]
        lines.append(
            f"| {phase_name} | {stable_label} | {phase['stop_reason']} | "
            f"{_fmt_pct(phase['peak_cpu_pct'])} | {_fmt_pct(phase['peak_iowait_pct'])} | "
            f"{_fmt_float(psi_peak)} | {_fmt_pct(phase['peak_io_util_pct'])} |"
        )
    lines.append("")

    lines.append("## Detailed Results")
    lines.append("")
    for phase_name in ("cpu", "memory", "disk"):
        phase = summary[phase_name]
        lines.append(f"### {phase_name.title()}")
        lines.append("")
        if phase_name == "cpu":
            lines.append("| Step | Duration | Stable | Avg CPU | Peak CPU | Peak iowait | Load/core | PSI cpu avg10 | Stop reason |")
            lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
            for result in phase["results"]:
                lines.append(
                    f"| {result['target_label']} | {_fmt_float(result['duration_s'])}s | {str(result['stable']).lower()} | "
                    f"{_fmt_pct(result['avg_cpu_pct'])} | {_fmt_pct(result['peak_cpu_pct'])} | {_fmt_pct(result['peak_iowait_pct'])} | "
                    f"{_fmt_float(result['avg_load_ratio'])} | {_fmt_float(result['peak_psi_cpu_some'])} | {result['stop_reason']} |"
                )
        elif phase_name == "memory":
            lines.append("| Step | Duration | Stable | Min available | Avg available | Peak mem pressure | Peak CPU | Stop reason |")
            lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
            for result in phase["results"]:
                lines.append(
                    f"| {result['target_label']} | {_fmt_float(result['duration_s'])}s | {str(result['stable']).lower()} | "
                    f"{_fmt_mib(result['min_mem_avail_mib'])} | {_fmt_mib(result['avg_mem_avail_mib'])} | "
                    f"{_fmt_float(result['peak_psi_mem_some'])} | {_fmt_pct(result['peak_cpu_pct'])} | {result['stop_reason']} |"
                )
        else:
            lines.append("| Step | Duration | Stable | Peak IO util | Peak await | Peak iowait | PSI io avg10 | Stop reason |")
            lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
            for result in phase["results"]:
                lines.append(
                    f"| {result['target_label']} | {_fmt_float(result['duration_s'])}s | {str(result['stable']).lower()} | "
                    f"{_fmt_pct(result['peak_io_util_pct'])} | {_fmt_float(result['peak_io_await_ms'])} ms | "
                    f"{_fmt_pct(result['peak_iowait_pct'])} | {_fmt_float(result['peak_psi_io_some'])} | {result['stop_reason']} |"
                )
        lines.append("")

    lines.append("## Recommended Ceiling")
    lines.append("")
    cpu_highest = summary["cpu"]["highest_stable"]
    mem_highest = summary["memory"]["highest_stable"]
    disk_highest = summary["disk"]["highest_stable"]
    if cpu_highest:
        lines.append(f"- CPU: keep at or below `{cpu_highest['target_label']}` for sustained use.")
    if mem_highest:
        lines.append(f"- Memory: keep resident usage at or below `{mem_highest['target_label']}` and leave at least `{_fmt_mib(config['memory_reserve_mib'])}` free.")
    if disk_highest:
        lines.append(f"- Disk: keep concurrent write workers at or below `{disk_highest['target_label']}`.")
    lines.append("- If any phase hits `safety_threshold`, treat the previous stable step as the practical ceiling.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- The test is intentionally conservative and stops on early pressure signals.")
    lines.append("- CPU, memory, and disk phases are isolated to avoid mixing bottlenecks.")
    lines.append("- The disk phase writes to temporary files under the configured workdir and removes them after each step.")
    lines.append("")
    return "\n".join(lines)


def _prepare_report_dict(args: argparse.Namespace, system: Dict[str, Any], cpu_summary: PhaseSummary, mem_summary: PhaseSummary, disk_summary: PhaseSummary) -> Dict[str, Any]:
    def _phase_to_dict(summary: PhaseSummary) -> Dict[str, Any]:
        highest = _pick_highest_stable(summary)
        peak_psi_cpu_some = max((result.peak_psi_cpu_some for result in summary.results), default=0.0)
        peak_psi_mem_some = max((result.peak_psi_mem_some for result in summary.results), default=0.0)
        peak_psi_io_some = max((result.peak_psi_io_some for result in summary.results), default=0.0)
        return {
            "name": summary.name,
            "unit": summary.unit,
            "stop_reason": summary.stop_reason,
            "peak_cpu_pct": max((result.peak_cpu_pct for result in summary.results), default=0.0),
            "peak_iowait_pct": max((result.peak_iowait_pct for result in summary.results), default=0.0),
            "peak_io_util_pct": max((result.peak_io_util_pct for result in summary.results), default=0.0),
            "peak_psi_cpu_some": peak_psi_cpu_some,
            "peak_psi_mem_some": peak_psi_mem_some,
            "peak_psi_io_some": peak_psi_io_some,
            "results": [
                {
                    "target_label": result.target_label,
                    "step": result.step,
                    "duration_s": result.duration_s,
                    "stable": result.stable,
                    "stop_reason": result.stop_reason,
                    "peak_cpu_pct": result.peak_cpu_pct,
                    "peak_iowait_pct": result.peak_iowait_pct,
                    "peak_io_util_pct": result.peak_io_util_pct,
                    "peak_io_await_ms": result.peak_io_await_ms,
                    "min_mem_avail_mib": result.min_mem_avail_mib,
                    "avg_mem_avail_mib": result.avg_mem_avail_mib,
                    "avg_cpu_pct": result.avg_cpu_pct,
                    "avg_load_ratio": result.avg_load_ratio,
                    "peak_psi_cpu_some": result.peak_psi_cpu_some,
                    "peak_psi_mem_some": result.peak_psi_mem_some,
                    "peak_psi_io_some": result.peak_psi_io_some,
                }
                for result in summary.results
            ],
            "highest_stable": (
                {
                    "target_label": highest.target_label,
                    "step": highest.step,
                    "duration_s": highest.duration_s,
                    "peak_cpu_pct": highest.peak_cpu_pct,
                    "peak_iowait_pct": highest.peak_iowait_pct,
                    "peak_io_util_pct": highest.peak_io_util_pct,
                    "peak_io_await_ms": highest.peak_io_await_ms,
                    "min_mem_avail_mib": highest.min_mem_avail_mib,
                    "avg_mem_avail_mib": highest.avg_mem_avail_mib,
                    "avg_cpu_pct": highest.avg_cpu_pct,
                    "avg_load_ratio": highest.avg_load_ratio,
                }
                if highest
                else None
            ),
        }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system,
        "config": {
            "baseline_seconds": args.baseline_seconds,
            "step_seconds": args.step_seconds,
            "cooldown_seconds": args.cooldown_seconds,
            "memory_reserve_mib": args.memory_reserve_mib,
            "disk_file_mib": args.disk_file_mib,
            "cpu_steps": args.cpu_steps_resolved,
            "memory_steps": args.memory_steps_resolved,
            "disk_steps": args.disk_steps_resolved,
        },
        "summary": {
            "cpu": _phase_to_dict(cpu_summary),
            "memory": _phase_to_dict(mem_summary),
            "disk": _phase_to_dict(disk_summary),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a conservative CPU, memory, and disk pressure test and write a Markdown summary.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="Markdown report output path.")
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR, help="Temporary working directory for test artifacts.")
    parser.add_argument("--baseline-seconds", type=int, default=15, help="Baseline sampling duration in seconds.")
    parser.add_argument("--step-seconds", type=int, default=20, help="Duration per pressure-test step in seconds.")
    parser.add_argument("--cooldown-seconds", type=int, default=5, help="Cooldown time between steps in seconds.")
    parser.add_argument("--memory-reserve-mib", type=int, default=2048, help="Minimum memory to keep free during the memory phase.")
    parser.add_argument("--disk-file-mib", type=int, default=128, help="Per-disk-worker file size in MiB.")
    parser.add_argument("--cpu-workers", default="", help="Comma-separated CPU worker counts. Default is derived from CPU count.")
    parser.add_argument("--memory-fractions", default="0.25,0.40,0.55,0.70,0.80", help="Comma-separated fractions of safe allocatable memory.")
    parser.add_argument("--disk-workers", default="1,2,4", help="Comma-separated disk worker counts.")
    args = parser.parse_args()

    args.report = args.report.expanduser().resolve()
    args.workdir = args.workdir.expanduser().resolve()
    args.cpu_workers = _parse_csv_ints(args.cpu_workers)
    args.memory_fractions = _parse_csv_floats(args.memory_fractions)
    args.disk_workers = _parse_csv_ints(args.disk_workers)

    hostname = platform.node()
    kernel = platform.release()
    cpu_count = max(os.cpu_count() or 1, 1)
    meminfo = _read_meminfo()
    total_mem_bytes = meminfo.get("MemTotal", 0) * 1024
    mem_available_bytes = meminfo.get("MemAvailable", 0) * 1024
    root_source = _root_source()
    root_fs = _root_fs_type()
    root_free_bytes = _root_free_bytes()
    root_device = _root_device_name()
    cgroup_dir = _cgroup_dir()
    cgroup_values = _read_cgroup_values(cgroup_dir)
    disk_file_mib = max(64, min(args.disk_file_mib, max(64, int(_safe_bytes_to_mib(root_free_bytes) / 32))))
    args.disk_file_mib = disk_file_mib

    args.workdir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    steps = _build_steps(args, _safe_bytes_to_mib(total_mem_bytes))
    args.cpu_steps_resolved = [step for step, _ in steps["cpu"]]
    args.memory_steps_resolved = [step for step, _ in steps["memory"]]
    args.disk_steps_resolved = [step for step, _ in steps["disk"]]

    stop_event = mp.Event()

    def _handle_signal(signum: int, _frame: Any) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    baseline_cpu = _read_proc_stat()
    baseline_disk = _read_diskstats(root_device)

    baseline_samples: List[Sample] = []
    start = time.perf_counter()
    baseline_prev_wall = start
    while time.perf_counter() - start < max(1, args.baseline_seconds) and not stop_event.is_set():
        sample, baseline_cpu, baseline_disk, baseline_prev_wall = _compute_sample(
            baseline_cpu,
            baseline_disk,
            baseline_prev_wall,
            root_device,
            cpu_count,
        )
        baseline_samples.append(sample)
        time.sleep(1.0)

    baseline_summary = {
        "duration_s": time.perf_counter() - start,
        "avg_cpu_pct": (sum(s.cpu_pct for s in baseline_samples) / len(baseline_samples)) if baseline_samples else 0.0,
        "peak_cpu_pct": max((s.cpu_pct for s in baseline_samples), default=0.0),
        "avg_iowait_pct": (sum(s.iowait_pct for s in baseline_samples) / len(baseline_samples)) if baseline_samples else 0.0,
        "peak_iowait_pct": max((s.iowait_pct for s in baseline_samples), default=0.0),
        "avg_mem_avail_mib": (sum(s.mem_avail_mib for s in baseline_samples) / len(baseline_samples)) if baseline_samples else 0.0,
        "min_mem_avail_mib": min((s.mem_avail_mib for s in baseline_samples), default=0.0),
        "avg_io_util_pct": (sum(s.io_util_pct for s in baseline_samples) / len(baseline_samples)) if baseline_samples else 0.0,
        "peak_io_util_pct": max((s.io_util_pct for s in baseline_samples), default=0.0),
        "peak_psi_cpu_some": max((s.psi_cpu_some for s in baseline_samples), default=0.0),
        "peak_psi_mem_some": max((s.psi_mem_some for s in baseline_samples), default=0.0),
        "peak_psi_io_some": max((s.psi_io_some for s in baseline_samples), default=0.0),
    }

    total_mem_mib = _safe_bytes_to_mib(total_mem_bytes)
    cpu_summary = _run_phase(
        phase="cpu",
        steps=steps["cpu"],
        baseline_cpu=baseline_cpu,
        baseline_disk=baseline_disk,
        root_device=root_device,
        cpu_count=cpu_count,
        baseline_mem_avail_mib=_safe_bytes_to_mib(mem_available_bytes),
        stop_event=stop_event,
        step_seconds=args.step_seconds,
        cooldown_seconds=args.cooldown_seconds,
        workdir=args.workdir,
        memory_reserve_mib=args.memory_reserve_mib,
        disk_file_mib=disk_file_mib,
    )
    mem_summary = _run_phase(
        phase="memory",
        steps=steps["memory"],
        baseline_cpu=baseline_cpu,
        baseline_disk=baseline_disk,
        root_device=root_device,
        cpu_count=cpu_count,
        baseline_mem_avail_mib=_safe_bytes_to_mib(mem_available_bytes),
        stop_event=stop_event,
        step_seconds=args.step_seconds,
        cooldown_seconds=args.cooldown_seconds,
        workdir=args.workdir,
        memory_reserve_mib=args.memory_reserve_mib,
        disk_file_mib=disk_file_mib,
    )
    disk_summary = _run_phase(
        phase="disk",
        steps=steps["disk"],
        baseline_cpu=baseline_cpu,
        baseline_disk=baseline_disk,
        root_device=root_device,
        cpu_count=cpu_count,
        baseline_mem_avail_mib=_safe_bytes_to_mib(mem_available_bytes),
        stop_event=stop_event,
        step_seconds=args.step_seconds,
        cooldown_seconds=args.cooldown_seconds,
        workdir=args.workdir,
        memory_reserve_mib=args.memory_reserve_mib,
        disk_file_mib=disk_file_mib,
    )

    system = {
        "hostname": hostname,
        "kernel": kernel,
        "cpu_count": cpu_count,
        "mem_total_bytes": total_mem_bytes,
        "mem_available_bytes": mem_available_bytes,
        "root_source": root_source,
        "root_fs": root_fs,
        "root_free_bytes": root_free_bytes,
        "cgroup_dir": str(cgroup_dir),
        "cgroup": cgroup_values,
    }
    report = _prepare_report_dict(args, system, cpu_summary, mem_summary, disk_summary)
    report["baseline"] = baseline_summary
    markdown = _make_markdown(report)
    args.report.write_text(markdown, encoding="utf-8")

    print(f"Markdown report written to: {args.report}")
    print(f"CPU highest stable: {report['summary']['cpu']['highest_stable']['target_label'] if report['summary']['cpu']['highest_stable'] else 'n/a'}")
    print(f"Memory highest stable: {report['summary']['memory']['highest_stable']['target_label'] if report['summary']['memory']['highest_stable'] else 'n/a'}")
    print(f"Disk highest stable: {report['summary']['disk']['highest_stable']['target_label'] if report['summary']['disk']['highest_stable'] else 'n/a'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
