# ✈️ 64×64 iDotMatrix Flight Display — UI Spec (v1)

## Goal

Design a clean, glanceable 64×64 display that shows the **most relevant nearby aircraft** using local ADS-B data.

Prioritize:

* readability at a distance
* real-time situational awareness
* minimal clutter
* strong visual hierarchy

---

## Display Modes

### 1. Default Mode (Primary)

**Layout: “Flight Card”**

```text
CALLSIGN

ALT   SPD   DIR

VERTICAL STATE
```

### Example

```text
UAL2215

18k   520kt   →

↑1500
```

### Fields

| Field     | Source                     | Notes                         |
| --------- | -------------------------- | ----------------------------- |
| Callsign  | `flight`                   | Fallback to hex               |
| Altitude  | `alt_baro`                 | Format as `18k`, `4.9k`       |
| Speed     | `gs`                       | Show in knots (`520kt`)       |
| Direction | `track`                    | Arrow (↑ → ↓ ←)               |
| Vertical  | `baro_rate` or `geom_rate` | Show `↑1500`, `↓2400`, or `—` |

---

## 2. Alert Mode (Override)

Triggered by notable conditions. Takes over entire display for 3–5 seconds.

### Triggers

* altitude < 5000 ft
* RSSI > -10 (very close)
* emergency squawk (7500/7600/7700)
* rapid descent/climb (>|2000 fpm|)

---

### Alert Types

#### Low Altitude

```text
LOW ✈

4.9k ↓
```

#### Overhead / Very Close

```text
OVERHEAD ✈

UAL2215
```

#### Emergency

```text
EMERGENCY

UAL2215
```

#### Rapid Descent

```text
DESCENT ↓↓

UAL2215
```

---

## 3. Idle Mode

When no valid aircraft:

```text
SCANNING ✈
```

or

```text
NO PLANES
```

---

## Visual Hierarchy

* **Large font:** callsign
* **Medium font:** altitude
* **Small font:** speed, direction, vertical rate

Guidelines:

* max 3 lines in default mode
* center align primary content
* avoid wrapping text
* prefer symbols over words

---

## Formatting Rules

### Callsign

* trim whitespace
* fallback to hex if missing

### Altitude

* `<10k` → `4.9k`
* multiples → `32k`
* else → `18.8k`

### Direction

* convert `track` to:

  * ↑ (north)
  * → (east)
  * ↓ (south)
  * ← (west)

### Vertical Rate

* `> +200` → `↑####`
* `< -200` → `↓####`
* else → `—`

---

## Optional Enhancements (v1.1+)

### Proximity Indicator

Visual signal strength:

```text
●●●●○
```

### Aircraft Size

Append:

```text
UAL2215 [H]
```

### Rotation Mode

Cycle top 3 aircraft every 2–4 seconds.

---

## Behavior Rules

* Update display only when:

  * selected aircraft changes
  * text changes
  * alert triggers
* avoid flicker / rapid switching
* alerts override all other modes temporarily

---

## Non-Goals

* no origin/destination display (low value vs space)
* no long text strings
* no raw coordinates or verbose metadata

---

## Summary

The display should feel like a **mini air-traffic awareness panel**, not a data dump.

At a glance, the user should instantly understand:

* what aircraft is overhead
* how high it is
* where it’s going
* whether anything unusual is happening

---
