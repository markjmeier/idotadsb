# 64×64 iDotMatrix Flight Display — Layout + Rendering Spec

## Goal

Build a pixel-perfect renderer for a 64×64 iDotMatrix display that presents aircraft data in a clean, readable, aviation-inspired layout.

The system should:

* render structured layouts, not just raw strings
* support multiple display modes
* use fixed layout zones
* produce a matrix buffer that can later be sent to the iDotMatrix device
* support local preview in development

---

# 1. Display Model

## Screen

* Resolution: **64×64 pixels**
* Coordinate origin: **top-left**
* X increases to the right
* Y increases downward

## Rendering approach

Use a simple retained-mode renderer:

1. Build a `ScreenState` object from aircraft data
2. Convert that state into a layout
3. Render layout into a monochrome or RGB matrix buffer
4. Send buffer to display backend

The renderer should be separate from aircraft logic.

---

# 2. Display Modes

Support these modes:

* `default`
* `alert`
* `idle`
* `rotate` (same layout as default, different selected aircraft)

Each mode should render through a dedicated layout function.

---

# 3. Layout Spec

## A. Default Mode — “Flight Card”

### Visual structure

```text id="8k7870"
┌────────────────────────────────┐
│                                │
│          CALLSIGN              │
│                                │
│   ALT        SPD        DIR    │
│                                │
│          VERTICAL              │
│                                │
└────────────────────────────────┘
```

### Zone layout

Define fixed rectangular zones:

#### 1. Callsign zone

* x: `4`
* y: `4`
* w: `56`
* h: `18`
* alignment: centered horizontally
* font: largest available readable font

Content example:

```text id="vp6l6b"
UAL2215
```

#### 2. Telemetry row

Three equal columns:

##### Altitude cell

* x: `4`
* y: `26`
* w: `18`
* h: `12`
* alignment: centered

##### Speed cell

* x: `23`
* y: `26`
* w: `18`
* h: `12`
* alignment: centered

##### Direction cell

* x: `42`
* y: `26`
* w: `18`
* h: `12`
* alignment: centered

Content example:

```text id="uicqlm"
18k   520   →
```

#### 3. Vertical state zone

* x: `4`
* y: `44`
* w: `56`
* h: `12`
* alignment: centered

Examples:

```text id="4hiwqv"
↑1500
↓2400
LEVEL
—
```

---

## B. Alert Mode

Alert mode should take over the whole screen.

### Layout

```text id="nmphri"
┌────────────────────────────────┐
│                                │
│            ALERT               │
│                                │
│           VALUE/ICON           │
│                                │
│          FLIGHT/INFO           │
│                                │
└────────────────────────────────┘
```

### Zones

#### Alert title

* x: `4`
* y: `8`
* w: `56`
* h: `16`
* centered
* large font

Examples:

```text id="0e6onh"
LOW
EMERGENCY
OVERHEAD
DESCENT
```

#### Alert detail

* x: `4`
* y: `28`
* w: `56`
* h: `14`
* centered
* medium font

Examples:

```text id="zr3l8a"
4.9k ↓
7700
↓↓ 2400
```

#### Alert subtext

* x: `4`
* y: `46`
* w: `56`
* h: `10`
* centered
* small font

Examples:

```text id="s6gacm"
UAL2215
PJC65
```

---

## C. Idle Mode

### Layout

Centered single or double line:

```text id="6lh7ln"
SCANNING
✈
```

or

```text id="kvkpah"
NO PLANES
```

### Zones

* x: `4`
* y: `18`
* w: `56`
* h: `28`
* centered

---

# 4. Typography / Font Rules

## Font strategy

Use bitmap fonts only. Avoid dynamic font rendering in v1.

Support three font sizes:

* `large`
* `medium`
* `small`

Recommended approximate sizes:

* `large`: 8–10 px tall
* `medium`: 6–8 px tall
* `small`: 5–6 px tall

Cursor should either:

* use an existing bitmap font library, or
* define a simple internal bitmap font map for required characters

## Required character support

Need at minimum:

* A–Z
* 0–9
* space
* `→ ↑ ↓ ←`
* `-`
* `.`
* `✈` optional fallback if supported
* `[` `]` optional
* `k`

If arrow glyphs are hard, fallback to:

* `N E S W`
* `UP / DN`

## Typography rules

* Callsign should be largest
* Numeric values should be medium
* Labels or status should be small
* Keep all text uppercase where practical

---

# 5. Spacing and Alignment Rules

## General

* All major content centered unless explicitly defined otherwise
* Minimum outer padding: `4 px`
* Minimum vertical separation between rows: `4 px`

## Telemetry row

* Three columns should remain visually balanced even if content width differs
* Each field should be centered inside its cell, not manually padded with spaces

## Truncation

* If callsign exceeds available width:

  * first try smaller font
  * then truncate
  * do not wrap

---

# 6. Color / Brightness Rules

If display supports color:

* default text: white
* alert text: red or amber
* idle: dim white or blue

If color support is awkward, v1 may use monochrome only.

Allow later support for:

* alert-specific colors
* dim/night mode
* brightness scaling

---

# 7. Rendering System

## Architecture

Implement the renderer in layers:

### A. Screen state

A semantic model, not pixels.

Example:

```python id="dd1m9q"
@dataclass
class ScreenState:
    mode: str
    callsign: str | None = None
    altitude_text: str | None = None
    speed_text: str | None = None
    direction_text: str | None = None
    vertical_text: str | None = None
    alert_title: str | None = None
    alert_detail: str | None = None
    alert_subtext: str | None = None
```

### B. Layout tree

Convert semantic state into positioned elements.

Example:

```python id="2yv8ma"
@dataclass
class TextElement:
    text: str
    x: int
    y: int
    w: int
    h: int
    font: str
    align: str = "center"
```

Optional root model:

```python id="1dy9jj"
@dataclass
class Layout:
    elements: list[TextElement]
```

### C. Matrix buffer

Render layout into a 64×64 buffer.

Suggested representation:

```python id="kgm4kz"
MatrixBuffer = list[list[int]]
```

For RGB:

```python id="o9f6cw"
MatrixBuffer = list[list[tuple[int, int, int]]]
```

Monochrome first is fine.

---

# 8. Renderer Responsibilities

Renderer should:

* clear the buffer
* render text into bounded zones
* center text horizontally in zones
* support font selection
* clip anything that exceeds bounds
* return a final matrix buffer

Renderer should not:

* know about ADS-B
* fetch data
* decide aircraft ranking
* manage Bluetooth transport

---

# 9. Preview / Development Mode

Very important: support local preview without hardware.

Cursor should implement one or both:

## Option A: terminal preview

Render the 64×64 buffer as ASCII blocks in the terminal.

## Option B: image preview

Render the matrix buffer to a PNG using Pillow for local development.

Recommended:

* implement PNG preview for accuracy
* save frames to a `preview/` folder

Example:

```text id="rz2gxp"
preview/default.png
preview/alert_low.png
preview/idle.png
```

This will make layout iteration much easier.

---

# 10. Suggested Module Structure

```text id="5vj5x2"
app/
  render/
    __init__.py
    screen_state.py
    layout.py
    fonts.py
    renderer.py
    preview.py
```

## File responsibilities

### `screen_state.py`

Defines semantic display state models.

### `layout.py`

Defines layout constants and helper functions:

* `build_default_layout(state)`
* `build_alert_layout(state)`
* `build_idle_layout(state)`

### `fonts.py`

Bitmap fonts and glyph metrics.

### `renderer.py`

Turns layouts into matrix buffers.

### `preview.py`

Writes PNG previews or terminal previews.

---

# 11. Rendering Rules for Text

## Text placement

For each text element:

1. measure glyph width
2. compute aligned x-position inside bounding box
3. render glyph pixels into buffer
4. clip at buffer edges

## Alignment support

Need at least:

* `left`
* `center`
* `right`

V1 mostly uses `center`.

## Text overflow

If text does not fit:

1. try smaller font
2. if still too long, truncate safely

---

# 12. Sample States

## Default

```python id="gcokys"
ScreenState(
    mode="default",
    callsign="UAL2215",
    altitude_text="18k",
    speed_text="520",
    direction_text="→",
    vertical_text="↑1500",
)
```

## Alert

```python id="5buj7r"
ScreenState(
    mode="alert",
    alert_title="LOW",
    alert_detail="4.9k ↓",
    alert_subtext="PJC65",
)
```

## Idle

```python id="mlnu2z"
ScreenState(
    mode="idle",
)
```

---

# 13. Acceptance Criteria

This work is successful when:

1. Cursor can generate a valid matrix buffer for:

   * default mode
   * alert mode
   * idle mode
2. Text is aligned predictably inside layout zones
3. Callsign is visually dominant
4. Telemetry row is readable and balanced
5. Alert mode is visually distinct
6. Layout can be previewed locally without hardware
7. Renderer is decoupled from transport and data-fetch logic

---

# 14. Cursor Prompt

Build a rendering subsystem for a 64×64 iDotMatrix flight display. Use a layered design: semantic `ScreenState` -> positioned layout elements -> matrix buffer renderer. Implement pixel-perfect layouts for default, alert, and idle modes using fixed zones and bitmap fonts. Add local preview support by exporting rendered frames to PNG. Keep the renderer fully separate from aircraft fetching and scoring logic. Prioritize centered alignment, readability, simple typography hierarchy, and easy future iteration.
