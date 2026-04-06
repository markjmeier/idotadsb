# 64×64 Layout Contract

Use a strict pixel grid. The screen is exactly 64 pixels wide by 64 pixels tall.

Coordinate system:

* origin is top-left
* x increases left to right
* y increases top to bottom
* valid x range: 0–63
* valid y range: 0–63

Do not think in terms of HTML/CSS rows and columns.
Think in terms of **rectangles on a bitmap**.

## Layout zones

Define these exact bounding boxes:

### Callsign box

* x: 0
* y: 0
* width: 64
* height: 20

Purpose:

* display the callsign only
* text must be centered horizontally and vertically inside this box
* callsign is the visually dominant element
* use largest font that fits
* if it does not fit, try the next smaller font
* if still too long, truncate safely

### Altitude box

* x: 0
* y: 20
* width: 21
* height: 20

Purpose:

* display altitude text like `18k` or `4.9k`
* centered horizontally and vertically inside the box

### Speed box

* x: 21
* y: 20
* width: 22
* height: 20

Purpose:

* display speed text like `520`
* centered horizontally and vertically inside the box

### Direction box

* x: 43
* y: 20
* width: 21
* height: 20

Purpose:

* display direction arrow like `→`
* centered horizontally and vertically inside the box

### Status / vertical box

* x: 0
* y: 40
* width: 64
* height: 24

Purpose:

* display vertical state like `↑1500`, `↓2400`, or `LEVEL`
* centered horizontally and vertically inside this box

## Required rendering behavior

For every box:

1. measure text width and height using the selected bitmap font
2. compute the draw origin so text is centered in the box
3. clip any pixels that fall outside the 64×64 display
4. never let text overflow into another box intentionally

## Fitting algorithm

For text placement in a box:

1. try `large` font
2. if text width > box width or text height > box height, try `medium`
3. if still too large, try `small`
4. if still too large, truncate text and append nothing
5. do not wrap text to a second line unless the box explicitly allows multiline

## Rendering API

Implement a generic function like:

```python
draw_text_in_box(
    buffer,
    text,
    box=(x, y, width, height),
    font_priority=["large", "medium", "small"],
    h_align="center",
    v_align="center",
    multiline=False,
)
```

This function should:

* choose the largest font that fits
* calculate centered placement
* render text into the buffer
* clip safely to screen bounds

## Data mapping

Default mode maps data into boxes like this:

* callsign -> Callsign box
* altitude_text -> Altitude box
* speed_text -> Speed box
* direction_text -> Direction box
* vertical_text -> Status / vertical box

## Example

For:

* callsign = `UAL2215`
* altitude_text = `18k`
* speed_text = `520`
* direction_text = `→`
* vertical_text = `↑1500`

Render using:

* callsign in box `(0, 0, 64, 20)`
* altitude in box `(0, 20, 21, 20)`
* speed in box `(21, 20, 22, 20)`
* direction in box `(43, 20, 21, 20)`
* vertical in box `(0, 40, 64, 24)`

## Important constraint

Do not manually position each string with ad hoc x/y values in the mode renderer.
Instead, define the boxes once and always render text by calling `draw_text_in_box(...)`.


# Revised layout, v2

# ✈️ Revised 64×64 Display Layout (v2)

## Design Goals

* Maximize readability at a glance
* Reduce redundancy (no duplicate climb indicators)
* Group related data logically
* Use full 64×64 space with clear hierarchy

---

# Layout Structure

## Final Layout

```text
CALLSIGN

ALTITUDE

STATE   SPEED   DIRECTION
```

---

## Example

```text
UAL2215

18k

CLIMB   520kt   SW
```

---

# Layout Zones (Strict Pixel Boxes)

## 1. Callsign (Primary)

* x: 0
* y: 0
* width: 64
* height: 24

Rules:

* largest font available
* centered horizontally and vertically
* fallback to smaller font if needed
* truncate if still too long

---

## 2. Altitude (Secondary)

* x: 0
* y: 24
* width: 64
* height: 16

Rules:

* medium-large font
* centered
* format:

  * `4900` → `4.9k`
  * `18000` → `18k`

---

## 3. Status Row (Tertiary)

Three columns:

### State (left)

* x: 0
* y: 40
* width: 21
* height: 24

Values:

* `CLIMB`
* `DESC`
* `LEVEL`

Derived from vertical rate:

* > +200 fpm → CLIMB
* < -200 fpm → DESC
* otherwise → LEVEL

---

### Speed (center)

* x: 21
* y: 40
* width: 22
* height: 24

Format:

```text
520kt
```

---

### Direction (right)

* x: 43
* y: 40
* width: 21
* height: 24

Use cardinal directions instead of arrows:

* N, NE, E, SE, S, SW, W, NW

Derived from `track`:

* 0–22.5 → N
* 22.5–67.5 → NE
* etc.

---

# Removed Elements

## ❌ Vertical rate display

Reason:

* redundant with state (CLIMB/DESC)
* visually noisy
* less useful at a glance

---

# Optional Enhancement (v1.1)

If you still want vertical rate:

Add it subtly:

```text
CLIMB   520kt   SW
        +1500
```

Rules:

* smaller font
* only shown when |rate| > 1000
* positioned under speed

---

# Rendering Rules

* Each field must render strictly inside its bounding box
* Text must be centered within each box
* No manual x/y tuning outside layout definitions
* Use a shared function:

```python
draw_text_in_box(buffer, text, box, font_priority)
```

---

# Data Mapping

| Field     | Source                    |
| --------- | ------------------------- |
| callsign  | `flight`                  |
| altitude  | `alt_baro`                |
| state     | `baro_rate` / `geom_rate` |
| speed     | `gs`                      |
| direction | `track`                   |

---

# Summary

This layout improves clarity by:

* making callsign dominant
* isolating altitude for quick scanning
* grouping motion into one cohesive row
* removing redundant vertical rate clutter

The result should feel like a clean aviation instrument, not a data dump.
