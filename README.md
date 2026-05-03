# Window Detector

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that detects open windows using temperature sensors — no physical contact sensor required.

## How it works

Most open-window detections in HA use a simple derivative threshold: if temperature drops fast, the window is open. This works for detecting the *opening event* but fails to maintain the state reliably — the derivative returns to near-zero within minutes even with the window still open, causing jitter.

This integration uses a **dual-score accumulator** with independent open and close scores:

- Each minute, evidence is gathered from three signals:
  - **Instantaneous derivative** (fast, catches the opening event)
  - **10-minute cumulative temperature change** (primary sustained signal)
  - **20-minute cumulative temperature change** (corroboration)
- Each score decays independently each minute so old evidence fades
- The **open** score must exceed a threshold to trigger open; the **close** score must independently exceed its own threshold to close — they don't share state
- When open and the room has equilibrated near outdoor temperature (window open a long time), close evidence is suppressed to prevent premature dropout

Tuned against real sensor data: **F1=95%, Precision=96%, Recall=95%**.

## Requirements

- A room temperature sensor (required)
- An outdoor temperature sensor or weather integration (required)
- A second indoor reference sensor from another room (optional, improves accuracy)

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations** → three-dot menu → **Custom repositories**
2. Add your repository URL, category: **Integration**
3. Search for "Window Detector" and install
4. Restart Home Assistant

### Manual

Copy the `custom_components/window_detector` folder to your HA `custom_components` directory and restart.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Window Detector**
3. Select your room temperature sensor and outdoor temperature sensor
4. Optionally select a reference indoor sensor (e.g. a sensor in a room with no window)

## Tuning

After setup, click **Configure** on the integration to adjust detection parameters. The defaults are calibrated from real data but you may want to adjust them for your environment:

| Parameter | Default | Effect |
|---|---|---|
| Open threshold | 18 | Higher = fewer false positives, slower detection |
| Close threshold | 15 | Higher = less mid-period dropout |
| Open decay | 0.85 | Lower = evidence fades faster (per minute) |
| Close decay | 0.88 | Lower = close evidence fades faster |
| Equilibrium delta | 7 °C | Suppress close evidence when room is within this of outdoor |
| Equilibrium suppress | 2 | Evidence points removed per tick when equilibrated |

## Diagnostic attributes

The binary sensor exposes `open_score` and `close_score` as state attributes so you can watch the scores in real time while tuning.

## Limitations

- Requires a meaningful indoor/outdoor temperature difference. Detection is less reliable in summer when inside ≈ outside temperature.
- The integration maintains score state in memory only — scores reset to zero on HA restart. The sensor will re-detect correctly within a few minutes.
- Score state is per-process; it does not persist across restarts.
