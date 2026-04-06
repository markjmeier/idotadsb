# ✈️ Display Timing, Rotation, and Airline Color Spec (v3)

## Goals

* Make the display feel dynamic and alive
* Avoid excessive API calls
* Keep aircraft selection stable and intentional
* Use airline-inspired accent colors to make the screen more recognizable at a glance

---

# 1. Core Timing Model

There are **two independent timers**:

## A. Card Rotation Timer (fast)

Controls how often the display switches between cards.

* default: **3 seconds**
* configurable in `.env`
* intended range: **2–4 seconds**

## B. Aircraft Selection Timer (slow)

Controls how often we pick a new aircraft.

* default: **60 seconds**
* configurable in `.env`

---

# 2. Behavior Summary

For a selected aircraft:

* Rotate between:

  * **Card A (Live)**
  * **Card B (Identity)**

Every:

```env id="341d0y"
CARD_ROTATION_SECONDS=3
```

Switch to a new aircraft every:

```env id="95l2ee"
AIRCRAFT_HOLD_SECONDS=60
```

---

# 3. Example Timeline

```text id="7m79hz"
Time 0s   → Select aircraft (UAL2215)
Time 0s   → Show Card A
Time 3s   → Show Card B
Time 6s   → Show Card A
Time 9s   → Show Card B
...
Time 60s  → Select new aircraft
```

---

# 4. Configuration (.env)

```env id="k9qlz2"
CARD_ROTATION_SECONDS=3
AIRCRAFT_HOLD_SECONDS=60

ENABLE_AIRLINE_COLORS=true
DEFAULT_TEXT_COLOR=255,255,255
DEFAULT_ACCENT_COLOR=180,200,255
ALERT_COLOR=255,80,80
CLIMB_COLOR=255,191,0
DESCENT_COLOR=80,200,255
LEVEL_COLOR=120,255,120
UNKNOWN_AIRLINE_COLOR=200,200,200
```

Optional:

```env id="qv6g09"
MIN_CARD_ROTATION_SECONDS=2
MAX_CARD_ROTATION_SECONDS=4
```

---

# 5. Selection Lock Behavior

Once an aircraft is selected:

* lock it for `AIRCRAFT_HOLD_SECONDS`
* do NOT switch during this window

### Exception (early override allowed)

Immediately replace current aircraft if:

* emergency squawk (7500/7600/7700)
* altitude < low threshold
* RSSI exceeds strong threshold

This ensures important events interrupt the rotation.

---

# 6. Card Rotation Logic

## Base rule

Alternate between cards:

```python id="3jth2t"
card_index = (elapsed_time // CARD_ROTATION_SECONDS) % 2
```

Where:

* `0 = Card A (Live)`
* `1 = Card B (Identity)`

## Fallback behavior

If **no enrichment data exists**:

* always show Card A
* disable rotation

---

# 7. State Model

```python id="9b9fyi"
@dataclass
class DisplayState:
    selected_aircraft_hex: str
    selected_callsign: str
    selected_at: float
    card_index: int
```

```python id="xz8qcg"
@dataclass
class TimingConfig:
    card_rotation_seconds: int
    aircraft_hold_seconds: int
```

---

# 8. Main Loop Logic

Every tick (e.g. 1 second):

1. Fetch local ADS-B data
2. Check if current aircraft expired:

   * if `now - selected_at > AIRCRAFT_HOLD_SECONDS`
   * select new aircraft
3. Check for override conditions:

   * if triggered → replace immediately
4. Determine current card:

   * based on rotation timer
5. Render appropriate card
6. Send to display

---

# 9. Enrichment Strategy Alignment

Because aircraft changes only every 60 seconds:

* only perform enrichment when:

  * a **new aircraft is selected**
* cache enrichment results
* do not re-fetch during the hold window

This guarantees:

* at most roughly **1 external lookup per minute**
* usually much less due to caching

---

# 10. Card Definitions

## Card A (Live)

Purpose: what the aircraft is doing right now

Example:

```text id="nqarf0"
UAL2215
18k
CLIMB 299kt W
```

Fields:

* callsign
* altitude
* motion state
* speed
* cardinal direction

## Card B (Identity)

Purpose: what the aircraft is

Example:

```text id="k7uw10"
UAL2215
A320
EWR→ORD
```

If route unavailable:

```text id="e60k2s"
UAL2215
A320
UNITED
```

If type unavailable:

```text id="h5e56g"
UAL2215
EWR→ORD
UNITED
```

If enrichment unavailable:

* keep showing Card A only

---

# 11. Airline Color Mapping

Use the airline prefix from the callsign to determine the accent color.

Example:

* `UAL2215` → prefix `UAL`
* `JBU816` → prefix `JBU`
* `FDX1234` → prefix `FDX`

These colors do **not** need to be exact official brand colors.
Use **airline-inspired display colors** that are visually recognizable and look good on the matrix.

## Rules

* Accent color primarily applies to:

  * callsign
  * optional small accent line / divider / icon
* All other informational text can remain white unless special state color is needed
* If no match exists, use `UNKNOWN_AIRLINE_COLOR`

## Suggested airline color map

```python id="8abvnx"
AIRLINE_COLORS = {
    # US majors
    "UAL": (0, 70, 160),      # United-inspired blue
    "AAL": (0, 102, 180),     # American-inspired blue
    "DAL": (200, 30, 60),     # Delta-inspired red
    "JBU": (0, 110, 220),     # JetBlue-inspired blue
    "SWA": (255, 180, 0),     # Southwest-inspired gold
    "ASA": (0, 120, 90),      # Alaska-inspired green
    "FFT": (0, 160, 60),      # Frontier-inspired green
    "NKS": (255, 220, 0),     # Spirit-inspired yellow
    "MXY": (255, 120, 0),     # Breeze-inspired orange
    "RPA": (110, 110, 160),   # Republic Airways-inspired muted indigo
    "EDV": (120, 140, 180),   # Endeavor-inspired soft blue-gray
    "ASH": (150, 50, 160),    # Mesa / regional purple-inspired
    "SKW": (100, 130, 180),   # SkyWest-inspired steel blue
    "JIA": (70, 120, 200),    # PSA / regional blue accent
    "GJS": (120, 150, 210),   # GoJet-inspired pale blue

    # Cargo
    "FDX": (120, 60, 180),    # FedEx-inspired purple
    "UPS": (110, 80, 40),     # UPS-inspired brown/gold
    "ABX": (200, 60, 60),     # ABX-inspired red
    "GTI": (210, 160, 0),     # Atlas-inspired gold
    "5X":  (120, 60, 180),    # Optional alternate FedEx code if encountered

    # Business / private / charter
    "EJA": (150, 150, 150),   # NetJets-inspired silver
    "LXJ": (180, 180, 180),   # Flexjet-inspired light gray
    "VJA": (200, 200, 200),   # Vista / charter neutral
    "PJC": (170, 170, 170),   # charter neutral
    "XFL": (140, 140, 180),   # executive flight neutral

    # European carriers
    "BAW": (30, 60, 130),     # British Airways-inspired navy
    "VIR": (220, 40, 80),     # Virgin Atlantic-inspired red
    "IBE": (210, 170, 0),     # Iberia-inspired yellow/gold
    "AUA": (220, 40, 40),     # Austrian-inspired red
    "DLH": (20, 40, 120),     # Lufthansa-inspired navy
    "KLM": (0, 150, 255),     # KLM-inspired light blue
    "AFR": (0, 80, 160),      # Air France-inspired blue
    "EIN": (0, 140, 110),     # Aer Lingus-inspired green
    "RYR": (0, 70, 190),      # Ryanair-inspired blue
    "EZY": (255, 110, 0),     # easyJet-inspired orange
    "SAS": (0, 60, 140),      # SAS-inspired blue
    "FIN": (0, 90, 170),      # Finnair-inspired blue
    "TAP": (0, 150, 90),      # TAP-inspired green
    "THY": (210, 40, 40),     # Turkish-inspired red
    "ETD": (180, 140, 80),    # Etihad-inspired gold/tan
    "UAE": (180, 20, 20),     # Emirates-inspired red

    # Canadian / other common long-haul
    "ACA": (180, 20, 20),     # Air Canada-inspired red
    "WJA": (0, 140, 170),     # WestJet-inspired teal
}
```

---

# 12. Airline Prefix Parsing Rules

* Extract the leading alphabetic airline prefix from the callsign
* Usually the first 3 letters, e.g.:

  * `UAL2215` → `UAL`
  * `FDX45` → `FDX`
  * `BAW173` → `BAW`
* If no valid alphabetic prefix can be extracted:

  * use `UNKNOWN_AIRLINE_COLOR`

Suggested helper:

```python id="4e8tch"
def extract_airline_prefix(callsign: str) -> str | None:
    ...
```

---

# 13. Color Usage Rules

## Recommended v1

* callsign: airline accent color
* altitude: white
* aircraft type / route: white
* state text:

  * `CLIMB` → `CLIMB_COLOR`
  * `DESC` → `DESCENT_COLOR`
  * `LEVEL` → `LEVEL_COLOR`
* alerts:

  * use `ALERT_COLOR`

## Simpler fallback

If multi-color text layout is difficult:

* color only the callsign
* keep everything else white
* alerts can still override entire screen color

That is the preferred v1 behavior.

---

# 14. Rendering Summary

## Card A — Live

```text id="pvgg9s"
UAL2215
18k
CLIMB 299kt W
```

## Card B — Identity

```text id="iavh8j"
UAL2215
A320
EWR→ORD
```

Calls sign should use airline accent color when available.

---

# 15. Key Design Principle

**Fast card rotation, slow aircraft selection, restrained color.**

* rotate cards every few seconds
* keep the same aircraft for a minute
* enrich only on aircraft change
* use color to add identity, not chaos

---

# 16. Cursor Implementation Notes

Implement:

* two independent timers:

  * card rotation
  * aircraft hold
* enrichment only when selecting a new aircraft
* airline prefix parsing from callsign
* airline color mapping via a static dict
* fallback to neutral color when unknown
* color only the callsign first, unless rendering system makes more color easy

Most important rule:
**poll local ADS-B often, rotate the UI quickly, but change aircraft and call enrichment APIs slowly.**


#ADSBDB enrichment

# ADSBDB Enrichment Spec (v1)

## Goal

Enrich selected aircraft with:

* aircraft type (e.g. A320, B738)
* route (origin → destination)

This is **optional, best-effort data** layered on top of local ADS-B.

---

## When to Call ADSBDB

Only call ADSBDB when:

* a **new aircraft is selected**

Never call:

* on every ADS-B poll
* on every render loop
* during card rotation

---

## Input

Use available identifiers:

Priority:

1. `hex` (ICAO address)
2. `callsign` (flight)

Example:

```python
hex = "a94b51"
callsign = "UAL2215"
```

---

## Output Model

```python
@dataclass
class EnrichmentData:
    aircraft_type: str | None = None     # "A320"
    route: str | None = None             # "EWR→ORD"
    airline: str | None = None           # "United"
    fetched_at: float | None = None
```

---

## Caching

Required to prevent API abuse.

Rules:

* cache by `hex` (primary key)
* fallback cache by `callsign`
* TTL: **30–60 minutes**

Config:

```env
ENRICHMENT_CACHE_TTL_SECONDS=1800
```

Behavior:

* if cached → return immediately
* if not cached → fetch and store
* cache failures briefly (e.g. 5 minutes)

---

## Rate Limiting

Hard limits:

* max **1 request per aircraft selection**
* minimum interval between calls:

```env
ENRICHMENT_MIN_LOOKUP_INTERVAL_SECONDS=60
```

---

## Failure Handling

If ADSBDB:

* times out
* returns invalid data
* returns ambiguous results

Then:

* return `None`
* continue with local-only display
* do not retry immediately

Enrichment must **never block rendering**.

---

## Data Quality Rules

Treat ADSBDB as **best-effort**:

* route may be missing or incorrect
* aircraft type is usually reliable
* callsign matching may be ambiguous

Display rules:

* only show route if both origin AND destination exist
* otherwise fallback to airline or aircraft type
* do not display partial or low-confidence data

---

## Display Integration

Used only in **Card B (Identity)**:

Priority:

1. callsign
2. aircraft type
3. route

Examples:

### Full enrichment

```text
UAL2215
A320
EWR→ORD
```

### Type only

```text
UAL2215
A320
UNITED
```

### No enrichment

* do not render Card B
* stay on Card A only

---

## Feature Flag

```env
ENABLE_ADSBDB_ENRICHMENT=true
```

If disabled:

* skip all enrichment logic
* always show live card only

---

## Interface

```python
class ADSBDBEnricher:
    def get_enrichment(
        self,
        hex: str,
        callsign: str | None
    ) -> EnrichmentData | None:
        ...
```

Responsibilities:

* check cache
* enforce rate limits
* call ADSBDB if needed
* normalize response
* return structured data

---

## Key Rule

**Local ADS-B is the source of truth.
ADSBDB is optional enrichment.**

The system must work perfectly even if ADSBDB is:

* down
* slow
* returning bad data
