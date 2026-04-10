# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.0] - 2026-04-10

### Added
- `--interval` CLI flag to set a custom sampling interval (default: 1.0 s)
- `--output-dir` CLI flag to set a custom output directory
- `query_gpu_metrics()` function — isolates nvidia-smi querying from the main loop
- `run_monitor()` function — encapsulates the CSV write loop for clarity
- `requirements.txt` with `psutil>=5.9.0`
- `.gitignore` excluding `.venv/`, `results/`, and Python cache files

### Changed
- Moved path setup and argument parsing into `main()` — no more module-level globals
- GPU values are now explicitly unpacked (`*gpu`) instead of being concatenated as raw strings
- `get_system_info()` now parses the GPU VRAM split more robustly
- HTML dashboard `createChart` call formatting aligned for readability

### Removed
- Module-level global variables (`results_dir`, `output_csv`, `output_html`)

## [1.0.0] - 2026-04-01

### Added
- Initial release
- CPU, RAM, disk I/O, and network monitoring via `psutil`
- NVIDIA GPU monitoring (utilization, VRAM, decoder, temperature) via `nvidia-smi`
- CSV output with millisecond-precision timestamps
- Standalone HTML dashboard generation using Chart.js (10 charts, 2-column grid layout)
- System hardware info extraction (model, CPU name, GPU name/VRAM) at startup
