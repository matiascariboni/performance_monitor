# Hardware Performance Monitor

A lightweight CLI tool that records CPU, RAM, disk I/O, network, and NVIDIA GPU metrics at configurable intervals and generates a standalone interactive HTML dashboard from the collected data.

## Features

- Samples CPU usage, RAM, disk read/write, and network in/out via `psutil`
- Samples GPU compute, video decoder (NVDEC), VRAM, and temperature via `nvidia-smi`
- Saves all metrics to a timestamped CSV file
- Generates a self-contained HTML dashboard (Chart.js) on exit
- Configurable sampling interval and output directory via CLI flags

## Requirements

- Python 3.8+
- `psutil` (see [requirements.txt](requirements.txt))
- NVIDIA GPU + drivers with `nvidia-smi` on `PATH` (GPU metrics fall back to zero if unavailable)
- Windows (system info uses `systeminfo` and `wmic`; core monitoring works on any OS)

## Installation

```bash
git clone https://github.com/matiascariboni/performance_monitor.git
cd performance_monitor
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Usage

```bash
python main.py [--interval SECONDS] [--output-dir PATH]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--interval` | `1.0` | Sampling interval in seconds |
| `--output-dir` | `./results` | Directory where CSV and HTML files are saved |

### Examples

```bash
# Default: 1-second interval, output to ./results/
python main.py

# 0.5-second interval
python main.py --interval 0.5

# Custom output directory
python main.py --output-dir /tmp/perf_run
```

Press **Ctrl+C** at any time to stop collection. The tool will immediately generate `dashboard.html` from the recorded CSV.

## Output

| File | Description |
|------|-------------|
| `results/performance_monitor_results.csv` | Raw metrics, one row per sample |
| `results/dashboard.html` | Interactive line charts, open in any browser |

### CSV columns

`Timestamp`, `CPU_Usage_Percent`, `RAM_Used_MB`, `RAM_Total_MB`, `Disk_Read_MBs`, `Disk_Write_MBs`, `Net_Recv_MBs`, `Net_Sent_MBs`, `GPU_Util_Percent`, `GPU_Mem_Util_Percent`, `GPU_Dec_Percent`, `GPU_Enc_Percent`, `GPU_VRAM_Used_MB`, `GPU_VRAM_Total_MB`, `GPU_Temp_C`

## License

MIT
