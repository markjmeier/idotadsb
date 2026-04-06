# ✈️ ADS-B iDotMatrix Flight Display

## Overview

Build a lightweight Python application that runs on a Raspberry Pi 4 and reads local ADS-B aircraft data from an existing receiver, then displays useful flight information on an iDotMatrix display over Bluetooth.

The system should:

* Use **local ADS-B data only** (no external APIs)
* Be **simple, resilient, and always-on**
* Be easy to extend for future experiments

---

## Data Source

Primary endpoint:

```
http://192.168.4.36/skyaware/data/aircraft.json
```

### Requirements

* Poll every 1 second (configurable)
* Handle timeouts and failures gracefully
* Continue running even if data is temporarily unavailable

---

## Aircraft Data Model

Normalize raw JSON into a safe internal model:

```python
class Aircraft:
    hex: str
    flight: str | None
    lat: float | None
    lon: float | None
    altitude_ft: int | None
    speed_kt: float | None
    track_deg: float | None
    rssi: float | None
    seen_s: float | None
    seen_pos_s: float | None
```

### Notes

* All fields optional except `hex`
* Must tolerate missing data
* Trim whitespace from `flight`

---

## Core Loop

Every cycle:

1. Fetch aircraft.json
2. Normalize aircraft records
3. Filter valid aircraft
4. Score/rank aircraft
5. Select display candidate(s)
6. Render to display
7. Sleep for poll interval

---

## Filtering Rules

Only consider aircraft that are:

* `seen <= 10` seconds (configurable)
* Prefer `seen_pos <= 10` if using position

Prioritize aircraft with:

* valid `flight`
* valid `rssi`
* valid `lat/lon` (optional but preferred)

Fallback:

* If no good aircraft → allow degraded entries

---

## Scoring Logic

Initial scoring priorities:

1. Highest `rssi` (closest)
2. Freshness (`seen`)
3. Has callsign
4. Has position

Keep scoring simple and readable.

Example:

```python
score = (
    rssi_weight * rssi +
    freshness_weight * (10 - seen) +
    callsign_bonus +
    position_bonus
)
```

---

## Display Modes

### 1. Closest Aircraft (default)

Display:

```
CALLSIGN ALTITUDE
```

Examples:

```
UAL2215 18k
JBU816 22k
N23SJ 8.2k
```

---

### 2. Rotate Top Aircraft

* Select top N aircraft (default: 3)
* Rotate every 2–4 seconds
* Only include valid, non-stale aircraft

---

### 3. Low Aircraft Alert

Trigger when:

* altitude < 5000 ft (configurable)
* OR rssi > -10 (configurable)

Display overrides normal mode:

```
LOW ✈
CALLSIGN ALT
```

Example:

```
LOW ✈
PJC65 4.9k
```

---

### 4. Idle Mode

If no aircraft:

```
NO PLANES
```

or

```
SCANNING
```

---

## Formatting Rules

### Callsign

* Strip whitespace
* Fallback to `hex` if missing

### Altitude

Format as:

* `4900` → `4.9k`
* `18825` → `18.8k`
* `32000` → `32k`

### Direction (optional v1)

Map `track_deg` to:

* ↑ → ↓ ←
  or
* N E S W

---

## Display Interface

Abstract display behind an interface:

```python
class Display:
    def connect(self): ...
    def show_text(self, text: str): ...
    def show_alert(self, text: str): ...
    def clear(self): ...
```

### Implementations

* `MockDisplay` → prints to console
* `IDotMatrixDisplay` → real Bluetooth device

### Requirements

* Auto-reconnect on failure
* Do not crash if display unavailable
* Allow running without hardware

---

## Configuration

Use environment variables with defaults:

```
DATA_SOURCE_URL=http://192.168.4.36/skyaware/data/aircraft.json
POLL_INTERVAL_SECONDS=1
STALE_SECONDS=10
STALE_POSITION_SECONDS=10
LOW_ALTITUDE_FEET=5000
HIGH_RSSI_THRESHOLD=-10
ROTATE_TOP_N=3
ROTATE_INTERVAL_SECONDS=3
DISPLAY_MODE=closest
ENABLE_DISTANCE=false
HOME_LAT=
HOME_LON=
LOG_LEVEL=INFO
```

---

## Error Handling

Must handle:

* HTTP errors
* invalid JSON
* missing fields
* empty aircraft list
* Bluetooth disconnects

Behavior:

* log error
* continue running
* retry next cycle

---

## State Management

Avoid flickering:

* Only update display when:

  * aircraft changes significantly
  * or text changes
  * or rotation interval elapsed

* Debounce rapid switching between similar aircraft

---

## Project Structure

```
app/
  main.py
  config.py
  aircraft_source.py
  aircraft_filter.py
  formatter.py
  display.py
  models.py
  utils.py

tests/
  test_formatter.py
  test_filter.py
```

---

## Development Requirements

* Python 3.9+
* Minimal dependencies (`requests`, optional BLE lib)
* Use type hints
* Use pytest for basic tests
* Keep code simple and readable

---

## Testing

At minimum:

* altitude formatting
* callsign formatting
* filtering logic
* scoring selection

---

## Acceptance Criteria (v1)

* Runs continuously on Raspberry Pi 4
* Successfully reads aircraft.json
* Displays at least one aircraft
* Handles missing/partial data
* Recovers from failures
* Works in mock mode
* Supports:

  * closest aircraft mode
  * low aircraft alert
  * idle fallback

---

## Implementation Phases

### Phase 1

* Project scaffold
* Config loader
* Fetch + normalize aircraft
* Mock display

### Phase 2

* Filtering + scoring
* Formatting
* Closest mode

### Phase 3

* Alert mode
* Rotation mode
* State management

### Phase 4

* iDotMatrix integration
* Bluetooth reconnect handling
* Tests + polish

---

## Cursor Prompt

Build a modular Python application that reads aircraft data from a local ADS-B JSON endpoint and displays the most relevant aircraft on an iDotMatrix display. Prioritize simplicity, resilience, and clean structure. Start with a mock display, then integrate Bluetooth. Implement filtering, scoring, closest-aircraft mode, low-aircraft alert mode, rotation mode, and idle fallback. Handle missing data and failures gracefully. Use type hints and pytest for core logic.

---
possible repo skeleton (you may adjust as necessary)

flight-display/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── aircraft_source.py
│   ├── aircraft_filter.py
│   ├── formatter.py
│   ├── display.py
│   └── utils.py
├── tests/
│   ├── test_formatter.py
│   └── test_filter.py
├── .env.example
├── requirements.txt
├── pytest.ini
├── README.md
└── SPEC.md

---

requirements.txt
(Suggested from chatgpt)
requests>=2.31.0
pytest>=8.0.0
python-dotenv>=1.0.1