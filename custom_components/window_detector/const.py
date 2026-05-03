"""Constants for the Window Detector integration."""

DOMAIN = "window_detector"

# Config entry keys
CONF_ROOM_TEMP = "room_temp_sensor"
CONF_OUTDOOR_TEMP = "outdoor_temp_sensor"
CONF_REFERENCE_TEMP = "reference_temp_sensor"  # optional second indoor sensor

# Tuning options (exposed in options flow)
CONF_OPEN_THRESHOLD = "open_score_threshold"
CONF_CLOSE_THRESHOLD = "close_score_threshold"
CONF_OPEN_DECAY = "open_score_decay"
CONF_CLOSE_DECAY = "close_score_decay"
CONF_EQUILIBRIUM_DELTA = "equilibrium_delta"
CONF_EQUILIBRIUM_SUPPRESS = "equilibrium_suppress"

# Defaults (tuned against April 2026 dataset, F1=95%)
DEFAULT_OPEN_THRESHOLD = 18.0
DEFAULT_CLOSE_THRESHOLD = 15.0
DEFAULT_OPEN_DECAY = 0.85
DEFAULT_CLOSE_DECAY = 0.88
DEFAULT_EQUILIBRIUM_DELTA = 7.0   # °C — if |room - outdoor| < this while open, suppress close evidence
DEFAULT_EQUILIBRIUM_SUPPRESS = 2  # evidence points to suppress

# Update interval
UPDATE_INTERVAL_SECONDS = 60

# History window for cumulative temp change
TC10_WINDOW_MINUTES = 10
TC20_WINDOW_MINUTES = 20
HISTORY_MINUTES = 25  # how far back we need to fetch
