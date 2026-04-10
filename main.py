import psutil
import subprocess
import csv
import time
import argparse
import os
import json
from datetime import datetime


def get_system_info() -> dict:
    """Extracts system model and hardware specs using systeminfo, wmic, and nvidia-smi."""
    try:
        sysinfo_out = subprocess.check_output(
            "systeminfo", shell=True, text=True, stderr=subprocess.DEVNULL
        )
        instance_model = "Unknown"
        for line in sysinfo_out.split('\n'):
            if "System Model:" in line or "Modelo del sistema:" in line:
                instance_model = line.split(":", 1)[1].strip()
                break
    except Exception:
        instance_model = "Unknown"

    try:
        cpu_out = subprocess.check_output(
            "wmic cpu get name", shell=True, text=True, stderr=subprocess.DEVNULL
        )
        cpu_lines = [line.strip() for line in cpu_out.split('\n') if line.strip()]
        cpu_name = cpu_lines[1] if len(cpu_lines) > 1 else "Unknown CPU"
    except Exception:
        cpu_name = "Unknown CPU"

    try:
        gpu_info = subprocess.check_output(
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader",
            shell=True, text=True, stderr=subprocess.DEVNULL
        ).strip().split('\n')[0]
        gpu_name, gpu_vram_str = gpu_info.split(',')
        gpu_name = gpu_name.strip()
        gpu_vram_gb = round(float(gpu_vram_str.replace('MiB', '').strip()) / 1024, 1)
    except Exception:
        gpu_name = "Unknown GPU"
        gpu_vram_gb = "N/A"

    return {
        "model": instance_model,
        "cpu": cpu_name,
        "cores": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / (1024 ** 3), 2),
        "gpu_name": gpu_name,
        "gpu_vram_gb": gpu_vram_gb,
    }


def query_gpu_metrics() -> list:
    """Returns [util%, mem_util%, decode%, encode%, vram_used_MB, vram_total_MB, temp_C, power_W]."""
    cmd = [
        'nvidia-smi',
        '--query-gpu=utilization.gpu,utilization.memory,utilization.decoder,'
        'utilization.encoder,memory.used,memory.total,temperature.gpu,power.draw',
        '--format=csv,noheader,nounits',
    ]
    try:
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        vals = [v.strip() for v in output.split(',')]
        if len(vals) >= 8 and not vals[7].replace('.', '', 1).isdigit():
            vals[7] = '0'
        return (vals + ['0'] * 8)[:8]
    except Exception:
        return ['0'] * 8


def run_monitor(output_csv: str, interval: float) -> None:
    """Collects metrics at the given interval and writes rows to output_csv."""
    last_disk = psutil.disk_io_counters()
    last_net = psutil.net_io_counters()
    last_time = time.time()

    psutil.cpu_percent()  # discard first call (always returns 0.0)
    time.sleep(interval)

    with open(output_csv, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp",
            "CPU_Usage_Percent", "CPU_Freq_MHz",
            "RAM_Used_MB", "RAM_Total_MB",
            "Swap_Used_MB", "Swap_Total_MB",
            "Disk_Read_MBs", "Disk_Write_MBs",
            "Net_Recv_MBs", "Net_Sent_MBs",
            "Process_Count",
            "GPU_Util_Percent", "GPU_Mem_Util_Percent", "GPU_Dec_Percent", "GPU_Enc_Percent",
            "GPU_VRAM_Used_MB", "GPU_VRAM_Total_MB", "GPU_Temp_C", "GPU_Power_W",
        ])

        while True:
            now = time.time()
            dt = now - last_time

            cpu = psutil.cpu_percent()
            freq = psutil.cpu_freq()
            cpu_freq_mhz = round(freq.current) if freq else 0

            ram = psutil.virtual_memory()
            swap = psutil.swap_memory()

            disk = psutil.disk_io_counters()
            disk_r = (disk.read_bytes - last_disk.read_bytes) / dt / (1024 * 1024)
            disk_w = (disk.write_bytes - last_disk.write_bytes) / dt / (1024 * 1024)

            net = psutil.net_io_counters()
            net_r = (net.bytes_recv - last_net.bytes_recv) / dt / (1024 * 1024)
            net_w = (net.bytes_sent - last_net.bytes_sent) / dt / (1024 * 1024)

            proc_count = len(psutil.pids())
            last_disk, last_net, last_time = disk, net, now

            gpu = query_gpu_metrics()

            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                cpu, cpu_freq_mhz,
                round(ram.used / (1024 * 1024), 2),
                round(ram.total / (1024 * 1024), 2),
                round(swap.used / (1024 * 1024), 2),
                round(swap.total / (1024 * 1024), 2),
                round(disk_r, 2), round(disk_w, 2),
                round(net_r, 2), round(net_w, 2),
                proc_count,
                *gpu,
            ])
            f.flush()
            time.sleep(interval)


def generate_html_dashboard(csv_path: str, html_path: str, sys_info: dict) -> None:
    """Reads the CSV and generates a standalone interactive HTML dashboard."""
    print("\n[+] Generating interactive HTML dashboard...")

    timestamps_full, timestamps = [], []
    cpu_usage, cpu_freq = [], []
    ram_used, swap_used = [], []
    disk_r, disk_w, net_r, net_w = [], [], [], []
    proc_count = []
    gpu_util, gpu_mem_util, gpu_enc, gpu_dec = [], [], [], []
    vram_used, gpu_temp, gpu_power = [], [], []
    total_ram_mb = total_swap_mb = total_vram_mb = 0

    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                ts = row["Timestamp"]
                timestamps_full.append(ts)
                timestamps.append(ts.split(" ")[1].split(".")[0])
                cpu_usage.append(float(row["CPU_Usage_Percent"]))
                cpu_freq.append(float(row.get("CPU_Freq_MHz", 0)))
                ram_used.append(float(row["RAM_Used_MB"]))
                swap_used.append(float(row.get("Swap_Used_MB", 0)))
                total_ram_mb = float(row["RAM_Total_MB"])
                total_swap_mb = float(row.get("Swap_Total_MB", 0))
                disk_r.append(float(row["Disk_Read_MBs"]))
                disk_w.append(float(row["Disk_Write_MBs"]))
                net_r.append(float(row["Net_Recv_MBs"]))
                net_w.append(float(row["Net_Sent_MBs"]))
                proc_count.append(int(row.get("Process_Count", 0)))
                gpu_util.append(float(row["GPU_Util_Percent"]))
                gpu_mem_util.append(float(row.get("GPU_Mem_Util_Percent", 0)))
                gpu_enc.append(float(row.get("GPU_Enc_Percent", 0)))
                gpu_dec.append(float(row.get("GPU_Dec_Percent", 0)))
                vram_used.append(float(row["GPU_VRAM_Used_MB"]))
                gpu_temp.append(float(row["GPU_Temp_C"]))
                gpu_power.append(float(row.get("GPU_Power_W", 0)))
    except Exception as e:
        print(f"[-] Error reading CSV: {e}")
        return

    n = len(timestamps)
    if n == 0:
        print("[-] No data to plot.")
        return

    session_start = timestamps_full[0]
    session_end = timestamps_full[-1]
    try:
        fmt = '%Y-%m-%d %H:%M:%S.%f'
        t0 = datetime.strptime(timestamps_full[0], fmt)
        t1 = datetime.strptime(timestamps_full[-1], fmt)
        total_sec = int((t1 - t0).total_seconds())
        hours, rem = divmod(total_sec, 3600)
        mins, secs = divmod(rem, 60)
        duration_str = f"{hours:02d}h {mins:02d}m {secs:02d}s" if hours else f"{mins:02d}m {secs:02d}s"
    except Exception:
        duration_str = "N/A"

    # Python → JS data bridge (f-string: only this block needs Python substitution)
    js_data = f"""
const labels       = {json.dumps(timestamps)};
const cpuData      = {json.dumps(cpu_usage)};
const cpuFreqData  = {json.dumps(cpu_freq)};
const ramData      = {json.dumps(ram_used)};
const swapData     = {json.dumps(swap_used)};
const diskRData    = {json.dumps(disk_r)};
const diskWData    = {json.dumps(disk_w)};
const netRData     = {json.dumps(net_r)};
const netWData     = {json.dumps(net_w)};
const procData     = {json.dumps(proc_count)};
const gpuUtilData  = {json.dumps(gpu_util)};
const gpuMemUtil   = {json.dumps(gpu_mem_util)};
const gpuEncData   = {json.dumps(gpu_enc)};
const gpuDecData   = {json.dumps(gpu_dec)};
const vramData     = {json.dumps(vram_used)};
const gpuTempData  = {json.dumps(gpu_temp)};
const gpuPowerData = {json.dumps(gpu_power)};
const totalRamMB   = {total_ram_mb};
const totalSwapMB  = {total_swap_mb};
const totalVramMB  = {total_vram_mb};
const SESSION_START = "{session_start}";
const SESSION_END   = "{session_end}";
const SESSION_DUR   = "{duration_str}";
const SAMPLE_COUNT  = {n};
"""

    # Header section (f-string for sys_info values)
    header_html = f"""    <header class="site-header">
        <div class="header-brand">
            <div class="brand-icon">&#9881;</div>
            <div>
                <h1>Hardware Performance Monitor</h1>
                <p class="header-sub">System performance analysis report</p>
            </div>
        </div>
        <div class="spec-grid">
            <div class="spec-item"><span class="spec-label">System</span><span class="spec-value">{sys_info['model']}</span></div>
            <div class="spec-item"><span class="spec-label">CPU</span><span class="spec-value">{sys_info['cpu']}</span></div>
            <div class="spec-item"><span class="spec-label">Cores</span><span class="spec-value">{sys_info['cores']} threads</span></div>
            <div class="spec-item"><span class="spec-label">RAM</span><span class="spec-value">{sys_info['ram_gb']} GB</span></div>
            <div class="spec-item"><span class="spec-label">GPU</span><span class="spec-value">{sys_info['gpu_name']}</span></div>
            <div class="spec-item"><span class="spec-label">VRAM</span><span class="spec-value">{sys_info['gpu_vram_gb']} GB</span></div>
        </div>
    </header>
"""

    # All static HTML/CSS/JS — regular strings, no f-string escaping needed
    html_head = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Performance Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --bg:      #0d1117;
            --surface: #161b22;
            --surface2:#21262d;
            --border:  #30363d;
            --text:    #e6edf3;
            --muted:   #8b949e;
            --radius:  10px;
        }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 24px;
        }

        /* ── Header ── */
        .site-header {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 24px 28px;
            margin-bottom: 16px;
            display: flex;
            flex-wrap: wrap;
            gap: 24px;
            align-items: flex-start;
            justify-content: space-between;
        }
        .header-brand { display: flex; align-items: center; gap: 16px; }
        .brand-icon   { font-size: 38px; line-height: 1; }
        h1            { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
        .header-sub   { font-size: 13px; color: var(--muted); margin-top: 3px; }
        .spec-grid    { display: grid; grid-template-columns: repeat(3, auto); gap: 8px 24px; }
        .spec-item    { display: flex; flex-direction: column; }
        .spec-label   { font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; color: var(--muted); }
        .spec-value   { font-size: 13px; font-weight: 600; margin-top: 2px; }

        /* ── Session bar ── */
        .session-bar {
            background: var(--surface2);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 11px 20px;
            margin-bottom: 16px;
            display: flex;
            flex-wrap: wrap;
            gap: 28px;
            font-size: 13px;
        }
        .s-item { display: flex; gap: 8px; align-items: center; }
        .s-label { color: var(--muted); }
        .s-value { font-weight: 600; font-variant-numeric: tabular-nums; }

        /* ── KPI cards ── */
        .kpi-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .kpi-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-top: 3px solid transparent;
            border-radius: var(--radius);
            padding: 15px 17px;
        }
        .kpi-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--muted); margin-bottom: 7px; }
        .kpi-value { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1; }
        .kpi-unit  { font-size: 12px; font-weight: 400; color: var(--muted); margin-left: 2px; }
        .kpi-sub   { font-size: 11px; color: var(--muted); margin-top: 5px; }

        /* ── Chart grid ── */
        .chart-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }

        .section-title {
            grid-column: 1 / -1;
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 0 2px;
        }
        .section-title h2 {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            color: var(--muted);
            font-weight: 600;
            white-space: nowrap;
        }
        .section-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }

        .chart-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 20px 20px 14px;
        }
        .chart-container { position: relative; height: 270px; }

        footer {
            text-align: center;
            padding: 28px 0 6px;
            font-size: 12px;
            color: var(--muted);
        }

        @media (max-width: 860px) {
            .chart-grid  { grid-template-columns: 1fr; }
            .spec-grid   { grid-template-columns: repeat(2, auto); }
            .kpi-row     { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
"""

    body_html = """    <div class="session-bar">
        <div class="s-item"><span class="s-label">Start</span><span class="s-value" id="sStart"></span></div>
        <div class="s-item"><span class="s-label">End</span><span class="s-value" id="sEnd"></span></div>
        <div class="s-item"><span class="s-label">Duration</span><span class="s-value" id="sDur"></span></div>
        <div class="s-item"><span class="s-label">Samples</span><span class="s-value" id="sSamples"></span></div>
    </div>

    <div class="kpi-row" id="kpiRow"></div>

    <div class="chart-grid">
        <div class="section-title"><h2>CPU</h2></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartCpu"></canvas></div></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartFreq"></canvas></div></div>

        <div class="section-title"><h2>Memory</h2></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartRam"></canvas></div></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartProc"></canvas></div></div>

        <div class="section-title"><h2>Network &amp; Disk I/O</h2></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartNet"></canvas></div></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartDisk"></canvas></div></div>

        <div class="section-title"><h2>GPU</h2></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartGpuEngines"></canvas></div></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartVram"></canvas></div></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartGpuTemp"></canvas></div></div>
        <div class="chart-card"><div class="chart-container"><canvas id="chartGpuPower"></canvas></div></div>
    </div>

    <footer>Generated by Hardware Performance Monitor</footer>
"""

    js_static = """
    Chart.defaults.color = 'rgba(255,255,255,0.55)';
    Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

    // Session info
    document.getElementById('sStart').textContent   = SESSION_START;
    document.getElementById('sEnd').textContent     = SESSION_END;
    document.getElementById('sDur').textContent     = SESSION_DUR;
    document.getElementById('sSamples').textContent = SAMPLE_COUNT.toLocaleString() + ' samples';

    // Stat helpers
    function avg(a)    { return a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0; }
    function peak(a)   { return a.length ? Math.max(...a) : 0; }
    function f1(n)     { return (+n).toFixed(1); }
    function f0(n)     { return Math.round(n).toLocaleString(); }
    function mb2gb(mb) { return (mb / 1024).toFixed(1); }

    // KPI cards
    const kpiDefs = [
        { label: 'CPU Avg',       val: () => f0(avg(cpuData)) + '%',           accent: '#f43f5e', sub: () => 'Peak ' + f0(peak(cpuData)) + '%' },
        { label: 'CPU Freq Avg',  val: () => f0(avg(cpuFreqData)) + ' MHz',    accent: '#fb923c', sub: () => 'Peak ' + f0(peak(cpuFreqData)) + ' MHz' },
        { label: 'RAM Peak',      val: () => mb2gb(peak(ramData)) + ' GB',     accent: '#34d399', sub: () => 'of ' + mb2gb(totalRamMB) + ' GB total' },
        { label: 'GPU Avg',       val: () => f0(avg(gpuUtilData)) + '%',       accent: '#a78bfa', sub: () => 'Peak ' + f0(peak(gpuUtilData)) + '%' },
        { label: 'VRAM Peak',     val: () => mb2gb(peak(vramData)) + ' GB',    accent: '#e879f9', sub: () => 'of ' + mb2gb(totalVramMB) + ' GB' },
        { label: 'GPU Peak Temp', val: () => f1(peak(gpuTempData)) + ' \u00b0C', accent: '#fb7185', sub: () => 'Avg ' + f1(avg(gpuTempData)) + ' \u00b0C' },
        { label: 'GPU Peak Power',val: () => f1(peak(gpuPowerData)) + ' W',    accent: '#fdba74', sub: () => 'Avg ' + f1(avg(gpuPowerData)) + ' W' },
        { label: 'Net Peak In',   val: () => f1(peak(netRData)) + ' MB/s',     accent: '#38bdf8', sub: () => 'Peak out ' + f1(peak(netWData)) + ' MB/s' },
    ];

    const kpiRow = document.getElementById('kpiRow');
    kpiDefs.forEach(k => {
        const el = document.createElement('div');
        el.className = 'kpi-card';
        el.style.borderTopColor = k.accent;
        el.innerHTML =
            '<div class="kpi-label">' + k.label + '</div>' +
            '<div class="kpi-value" style="color:' + k.accent + '">' + k.val() + '</div>' +
            '<div class="kpi-sub">'  + k.sub()  + '</div>';
        kpiRow.appendChild(el);
    });

    // Dataset factory
    function ds(label, data, color, secondary) {
        return {
            label: label,
            data: data,
            borderColor: color,
            backgroundColor: secondary ? 'transparent' : color + '15',
            borderWidth: secondary ? 1.5 : 2,
            tension: 0.3,
            fill: !secondary,
            pointRadius: 0,
            pointHitRadius: 12,
            pointHoverRadius: 4,
            pointHoverBackgroundColor: color,
        };
    }

    const xAxis = {
        ticks: { color: 'rgba(255,255,255,0.35)', maxTicksLimit: 10, maxRotation: 0, font: { size: 11 } },
        grid:  { color: 'rgba(255,255,255,0.05)' },
    };

    function yAxis(label, max) {
        const cfg = {
            title: { display: true, text: label, color: 'rgba(255,255,255,0.4)', font: { size: 11 } },
            ticks: { color: 'rgba(255,255,255,0.35)', font: { size: 11 } },
            grid:  { color: 'rgba(255,255,255,0.05)' },
            min: 0,
        };
        if (max != null) cfg.max = max;
        return cfg;
    }

    function mkChart(id, title, datasets, yLabel, yMax) {
        new Chart(document.getElementById(id), {
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    title: {
                        display: true, text: title,
                        color: 'rgba(255,255,255,0.85)',
                        font: { size: 13, weight: '600' },
                        padding: { top: 0, bottom: 12 },
                    },
                    legend: {
                        display: true,
                        labels: { color: 'rgba(255,255,255,0.6)', boxWidth: 13, padding: 14, font: { size: 11 } },
                    },
                    tooltip: {
                        backgroundColor: '#1a1d27',
                        titleColor: 'rgba(255,255,255,0.9)',
                        bodyColor:  'rgba(255,255,255,0.7)',
                        borderColor: 'rgba(255,255,255,0.12)',
                        borderWidth: 1,
                        padding: 10,
                        cornerRadius: 6,
                    },
                },
                scales: {
                    x: xAxis,
                    y: yAxis(yLabel, yMax != null ? yMax : null),
                },
            },
        });
    }

    var ramYMax = (totalRamMB + totalSwapMB) > 0 ? totalRamMB + totalSwapMB : null;
    var vramYMax = totalVramMB > 0 ? totalVramMB : null;

    mkChart('chartCpu',        'CPU Usage',
        [ds('CPU (%)', cpuData, '#f43f5e', false)],
        'Percentage (%)', 100);

    mkChart('chartFreq',       'CPU Clock Frequency',
        [ds('Frequency (MHz)', cpuFreqData, '#fb923c', false)],
        'MHz', null);

    mkChart('chartRam',        'System Memory',
        [ds('RAM Used (MB)', ramData, '#34d399', false),
         ds('Swap Used (MB)', swapData, '#6ee7b7', true)],
        'Megabytes (MB)', ramYMax);

    mkChart('chartProc',       'Active Processes',
        [ds('Process Count', procData, '#94a3b8', true)],
        'Count', null);

    mkChart('chartNet',        'Network Bandwidth',
        [ds('Received (MB/s)', netRData, '#38bdf8', false),
         ds('Sent (MB/s)',     netWData, '#818cf8', true)],
        'Bandwidth (MB/s)', null);

    mkChart('chartDisk',       'Disk I/O Speed',
        [ds('Read (MB/s)',  diskRData, '#fbbf24', false),
         ds('Write (MB/s)', diskWData, '#f59e0b', true)],
        'Speed (MB/s)', null);

    mkChart('chartGpuEngines', 'GPU Engine Utilization',
        [ds('Compute (%)', gpuUtilData, '#a78bfa', false),
         ds('Mem BW (%)',  gpuMemUtil,  '#818cf8', true),
         ds('Encoder (%)', gpuEncData,  '#f472b6', true),
         ds('Decoder (%)', gpuDecData,  '#38bdf8', true)],
        'Percentage (%)', 100);

    mkChart('chartVram',       'GPU Video Memory (VRAM)',
        [ds('VRAM Used (MB)', vramData, '#e879f9', false)],
        'Megabytes (MB)', vramYMax);

    mkChart('chartGpuTemp',    'GPU Temperature',
        [ds('Temperature (\u00b0C)', gpuTempData, '#fb7185', false)],
        'Celsius (\u00b0C)', null);

    mkChart('chartGpuPower',   'GPU Power Draw',
        [ds('Power (W)', gpuPowerData, '#fdba74', false)],
        'Watts (W)', null);
"""

    html_content = (
        html_head
        + header_html
        + body_html
        + "\n    <script>\n"
        + js_data
        + js_static
        + "    </script>\n"
        + "\n</body>\n</html>"
    )

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[+] Dashboard saved to: {html_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Hardware Performance Monitor — records CPU, RAM, disk, network, and GPU metrics."
    )
    parser.add_argument(
        "--interval", type=float, default=1.0,
        help="Sampling interval in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory for output files (default: <script_dir>/results)"
    )
    args = parser.parse_args()

    base_dir = args.output_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(base_dir, exist_ok=True)
    output_csv  = os.path.join(base_dir, "performance_monitor_results.csv")
    output_html = os.path.join(base_dir, "dashboard.html")

    print("[*] Gathering system hardware specifications...")
    sys_info = get_system_info()

    print("=" * 55)
    print("   HARDWARE PERFORMANCE MONITOR")
    print("=" * 55)
    print(f"  System   : {sys_info['model']}")
    print(f"  CPU      : {sys_info['cpu']}")
    print(f"  Cores    : {sys_info['cores']} threads")
    print(f"  RAM      : {sys_info['ram_gb']} GB")
    print(f"  GPU      : {sys_info['gpu_name']}")
    print(f"  VRAM     : {sys_info['gpu_vram_gb']} GB")
    print("-" * 55)
    print(f"  Output   : {base_dir}")
    print(f"  Interval : {args.interval}s")
    print("=" * 55)
    print("  Press Ctrl+C to stop and generate the HTML dashboard")
    print("=" * 55 + "\n")

    try:
        run_monitor(output_csv, args.interval)
    except KeyboardInterrupt:
        print("\n[OK] Monitoring stopped.")
        generate_html_dashboard(output_csv, output_html, sys_info)


if __name__ == "__main__":
    main()
