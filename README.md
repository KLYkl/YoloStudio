[English](README.md) | [中文](README.zh-CN.md)

# YoloStudio

A **PySide6 + Ultralytics YOLO** desktop application that brings dataset preparation, model training, and visual inference into a single GUI workflow.

> This repository is intended for source delivery. Model weights, runtime logs, inference outputs, temporary files, and machine-specific configuration are not tracked by default.

## Screenshots

### Model Training

Configure the training environment, model weights, dataset, and key hyperparameters from the GUI, with live command preview and training logs.

![YoloStudio training](docs/training.png)

### Data Preparation

Prepare datasets in one place with folder selection, class loading, statistics, frame extraction, augmentation, splitting, and image inspection before training.

![YoloStudio data preparation](docs/data-prep.png)

### Prediction

Run inference on images, videos, camera feeds, or screen capture with configurable confidence, IOU, output options, and batch-processing workflows.

![YoloStudio prediction](docs/prediction.png)

## Features

### 1. Data Preparation
- Dataset scanning and class statistics
- Batch label edit / replace / delete
- Dataset splitting
- Format conversion
- Image health checking
- Video frame extraction
- Data augmentation

### 2. Model Training
- GUI-based YOLO training configuration
- Automatic Conda environment discovery
- Real-time training log output
- Training workflow decoupled from the main UI thread

### 3. Prediction
- Image, video, camera, and screen input
- Key frame, result video, and report output
- Batch image / batch video processing

### 4. UI and Application Capabilities
- Dark / light theme switching
- Chinese / English language switching
- Global system log panel

## Tech Stack

- Python 3.10+
- PySide6
- Ultralytics
- PyTorch / TorchVision
- OpenCV

## Runtime Environment

The current codebase and startup flow are optimized for **Windows + Conda**, while most core Python modules remain largely cross-platform.

Recommended environment:

- Python 3.10
- Conda installed (optional but recommended)
- CUDA (optional, for GPU inference/training)

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Launch the app

```bash
python main.py
```

## Tests

Run tests with:

```bash
pytest tests -q
```

If `pytest` is not installed yet:

```bash
pip install pytest
```

Current tests mainly cover:
- Core data-processing logic
- Training environment detection
- Batch video result list generation
- Atomic writes and thread-pool cleanup

## Project Structure

```text
yolodo2.0/
├── main.py                 # application entry point
├── config.py               # global configuration
├── core/                   # core business logic
├── ui/                     # PySide6 UI
├── utils/                  # shared utilities
├── resources/              # static assets such as SVG files
├── tests/                  # automated tests
├── docs/                   # project documentation
└── requirements.txt
```

## Documentation

- User manual: [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md)
- Project report: [`docs/PROJECT_REPORT.md`](docs/PROJECT_REPORT.md)
- GitHub publish checklist: [`docs/GITHUB_PUBLISH_CHECKLIST.md`](docs/GITHUB_PUBLISH_CHECKLIST.md)

## Repository Notes

The following content is intentionally excluded from version control by default:

- Model weights such as `*.pt` and `*.onnx`
- Training / inference outputs such as `runs/` and `logs/`
- Local tool directories such as `.codex/`, `.agent/`, `.gemini/`
- Temporary / experimental directories such as `tmp/` and `scratch/`
- Machine-specific config and secrets such as `.env*` and `config.json`

## License

This repository is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
