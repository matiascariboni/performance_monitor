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
    # System Model
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

    # CPU Name
    try:
        cpu_out = subprocess.check_output(
            "wmic cpu get name", shell=True, text=True, stderr=subprocess.DEVNULL
        )
        cpu_lines = [line.strip() for line in cpu_out.split('\n') if line.strip()]
        cpu_name = cpu_lines[1] if len(cpu_lines) > 1 else "Unknown CPU"
    except Exception:
        cpu_name = "Unknown CPU"

    # GPU Name and VRAM
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
    """Queries nvidia-smi and returns [util, mem_util, decoder, encoder, vram_used, vram_total, temp]."""
    cmd = [
        'nvidia-smi',
        '--query-gpu=utilization.gpu,utilization.memory,utilization.decoder,'
        'utilization.encoder,memory.used,memory.total,temperature.gpu',
        '--format=csv,noheader,nounits',
    ]
    try:
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        return [v.strip() for v in output.split(',')]
    except Exception:
        return ["0", "0", "0", "0", "0", "0", "0"]


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
            "CPU_Usage_Percent", "RAM_Used_MB", "RAM_Total_MB",
            "Disk_Read_MBs", "Disk_Write_MBs",
            "Net_Recv_MBs", "Net_Sent_MBs",
            "GPU_Util_Percent", "GPU_Mem_Util_Percent", "GPU_Dec_Percent", "GPU_Enc_Percent",
            "GPU_VRAM_Used_MB", "GPU_VRAM_Total_MB", "GPU_Temp_C",
        ])

        while True:
            now = time.time()
            dt = now - last_time

            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory()

            disk = psutil.disk_io_counters()
            disk_r = (disk.read_bytes - last_disk.read_bytes) / dt / (1024 * 1024)
            disk_w = (disk.write_bytes - last_disk.write_bytes) / dt / (1024 * 1024)

            net = psutil.net_io_counters()
            net_r = (net.bytes_recv - last_net.bytes_recv) / dt / (1024 * 1024)
            net_w = (net.bytes_sent - last_net.bytes_sent) / dt / (1024 * 1024)

            last_disk, last_net, last_time = disk, net, now

            gpu = query_gpu_metrics()

            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                cpu,
                round(ram.used / (1024 * 1024), 2),
                round(ram.total / (1024 * 1024), 2),
                round(disk_r, 2),
                round(disk_w, 2),
                round(net_r, 2),
                round(net_w, 2),
                *gpu,
            ])
            f.flush()
            time.sleep(interval)


def generate_html_dashboard(csv_path: str, html_path: str, sys_info: dict) -> None:
    """Reads the CSV and generates a standalone interactive HTML dashboard."""
    print("\n[+] Generating interactive HTML dashboard...")

    timestamps, cpu_usage, ram_used = [], [], []
    disk_r, disk_w, net_r, net_w = [], [], [], []
    gpu_util, gpu_dec, vram_used, gpu_temp = [], [], [], []
    total_ram_mb = 0
    total_vram_mb = 0

    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                timestamps.append(row["Timestamp"].split(" ")[1].split(".")[0])
                cpu_usage.append(float(row["CPU_Usage_Percent"]))
                ram_used.append(float(row["RAM_Used_MB"]))
                total_ram_mb = float(row["RAM_Total_MB"])
                total_vram_mb = float(row["GPU_VRAM_Total_MB"])
                disk_r.append(float(row["Disk_Read_MBs"]))
                disk_w.append(float(row["Disk_Write_MBs"]))
                net_r.append(float(row["Net_Recv_MBs"]))
                net_w.append(float(row["Net_Sent_MBs"]))
                gpu_util.append(float(row["GPU_Util_Percent"]))
                gpu_dec.append(float(row["GPU_Dec_Percent"]))
                vram_used.append(float(row["GPU_VRAM_Used_MB"]))
                gpu_temp.append(float(row["GPU_Temp_C"]))
    except Exception as e:
        print(f"[-] Error reading CSV: {e}")
        return

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Performance Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f2f5; color: #333; margin: 0; padding: 30px; }}
        .header {{ background-color: #1e293b; color: white; padding: 25px; border-radius: 10px; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header h1 {{ margin: 0 0 15px 0; font-size: 28px; letter-spacing: 0.5px; }}
        .specs {{ display: flex; flex-wrap: wrap; gap: 15px; font-size: 15px; background: #334155; padding: 15px; border-radius: 8px; }}
        .specs span {{ background: #3b82f6; padding: 5px 10px; border-radius: 6px; font-weight: bold; color: white; }}
        .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 25px; }}
        .card {{ background: white; padding: 25px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
        .chart-container {{ position: relative; height: 350px; width: 100%; }}
        @media (max-width: 1200px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Hardware Performance Monitor</h1>
        <div class="specs">
            <div><strong>System Model:</strong> <span>{sys_info['model']}</span></div>
            <div><strong>Processor:</strong> <span>{sys_info['cpu']}</span></div>
            <div><strong>Cores:</strong> <span>{sys_info['cores']} vCPUs</span></div>
            <div><strong>Total RAM:</strong> <span>{sys_info['ram_gb']} GB</span></div>
            <div><strong>Graphics Card:</strong> <span>{sys_info['gpu_name']}</span></div>
            <div><strong>GPU VRAM:</strong> <span>{sys_info['gpu_vram_gb']} GB</span></div>
        </div>
    </div>

    <div class="grid">
        <div class="card"><div class="chart-container"><canvas id="chartCpu"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartRam"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartNetRecv"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartNetSent"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartGpuUtil"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartGpuDec"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartVram"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartGpuTemp"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartDiskRead"></canvas></div></div>
        <div class="card"><div class="chart-container"><canvas id="chartDiskWrite"></canvas></div></div>
    </div>

    <script>
        const labels = {json.dumps(timestamps)};

        const commonOptions = {{
            responsive: true,
            maintainAspectRatio: false,
            elements: {{ point: {{ radius: 0, hitRadius: 10, hoverRadius: 5 }} }},
            interaction: {{ mode: 'index', intersect: false }},
            plugins: {{ legend: {{ display: true, position: 'top' }} }}
        }};

        function createChart(ctxId, title, label, data, color, yAxisTitle, yMax = null) {{
            const options = JSON.parse(JSON.stringify(commonOptions));
            options.plugins.title = {{ display: true, text: title, font: {{ size: 16 }} }};
            options.scales = {{
                x: {{ title: {{ display: true, text: 'Time (HH:MM:SS)' }} }},
                y: {{ title: {{ display: true, text: yAxisTitle }}, min: 0 }}
            }};
            if (yMax !== null) options.scales.y.max = yMax;
            new Chart(document.getElementById(ctxId), {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: label,
                        data: data,
                        borderColor: color,
                        backgroundColor: color + '33',
                        borderWidth: 2,
                        tension: 0.2,
                        fill: true
                    }}]
                }},
                options: options
            }});
        }}

        createChart('chartCpu',       'CPU Usage',                'CPU (%)',          {json.dumps(cpu_usage)}, '#e74c3c', 'Percentage (%)', 100);
        createChart('chartRam',       'System Memory (RAM)',       'RAM Used (MB)',    {json.dumps(ram_used)},  '#2ecc71', 'Megabytes (MB)',  {total_ram_mb});
        createChart('chartNetRecv',   'Network Received',          'Inbound (MB/s)',   {json.dumps(net_r)},     '#3498db', 'Bandwidth (MB/s)');
        createChart('chartNetSent',   'Network Sent',              'Outbound (MB/s)',  {json.dumps(net_w)},     '#2980b9', 'Bandwidth (MB/s)');
        createChart('chartGpuUtil',   'GPU Core Usage',            'GPU Compute (%)', {json.dumps(gpu_util)},  '#9b59b6', 'Percentage (%)', 100);
        createChart('chartGpuDec',    'GPU Video Decoder (NVDEC)', 'Decode (%)',       {json.dumps(gpu_dec)},   '#8e44ad', 'Percentage (%)', 100);
        createChart('chartVram',      'GPU Video Memory (VRAM)',   'VRAM Used (MB)',   {json.dumps(vram_used)}, '#f1c40f', 'Megabytes (MB)',  {total_vram_mb});
        createChart('chartGpuTemp',   'GPU Temperature',           'Temperature (°C)', {json.dumps(gpu_temp)}, '#e67e22', 'Celsius (°C)',   100);
        createChart('chartDiskRead',  'Disk Read Speed',           'Read (MB/s)',      {json.dumps(disk_r)},    '#34495e', 'Speed (MB/s)');
        createChart('chartDiskWrite', 'Disk Write Speed',          'Write (MB/s)',     {json.dumps(disk_w)},    '#2c3e50', 'Speed (MB/s)');
    </script>
</body>
</html>"""

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
    output_csv = os.path.join(base_dir, "performance_monitor_results.csv")
    output_html = os.path.join(base_dir, "dashboard.html")

    print("[*] Gathering system hardware specifications...")
    sys_info = get_system_info()

    print("=" * 50)
    print("   HARDWARE PERFORMANCE MONITOR")
    print("=" * 50)
    print(f"Output directory : {base_dir}")
    print(f"CSV file         : {output_csv}")
    print(f"Sampling interval: {args.interval}s")
    print("--> Press Ctrl+C to stop and generate the HTML dashboard <--\n")

    try:
        run_monitor(output_csv, args.interval)
    except KeyboardInterrupt:
        print("\n[OK] Monitoring stopped.")
        generate_html_dashboard(output_csv, output_html, sys_info)


if __name__ == "__main__":
    main()
