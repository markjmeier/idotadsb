# Refactor roadmap (optional)

This file records **optional** structural improvements discussed for idotadsb. Nothing here is a bugfix or requirement.

**Policy:** Avoid refactors driven only by aesthetics. Prefer small, behavior-preserving steps; run **`pytest`** before and after; confirm scope with whoever maintains the branch.

---

## Why not only `docs/specs/`?

The **`docs/specs/`** directory is **gitignored** (local layout and product notes). Refactor and maintenance notes that should travel with the repo live under **`docs/`** as tracked files, e.g. this one.

---

## 1. `app/main.py` — `run_loop` decomposition

| | |
|--|--|
| **Status** | **Partially done:** panel resolution and refresh gating live in **`app/run_cycle.py`** (`resolve_panel_view`, `should_refresh_display`); `UiState` / `V3DisplayState` / `SquawkLatchState` moved there. `main.run_loop` still owns fetch, sleep, quiet-hours transitions, and `display.show_panel`. See **`tests/test_run_cycle.py`**. |
| **Idea** | *(Original)* Extract “given feed + settings + mutable state, compute the next `PanelView`” so the outer loop stays thin: fetch, call step, push if fingerprints changed. |
| **Follow-ups** | Further split (e.g. pure state machine with immutable snapshots) only if you need stronger isolation or more tests. |
| **Risk** | Medium for deeper refactors: state edges (e.g. `rotate_index` vs `card_epoch_mono`). |

---

## 2. `app/matrix_canvas.py` — split by responsibility

| | |
|--|--|
| **Idea** | Split along **panel kind** (v3 flight vs `alert_squawk` vs idle) or separate **layout/geometry** helpers from **PIL draw** calls. Exact split should follow how you actually edit the file (most churn wins). |
| **Why** | The module is one of the largest; multiple screen types in one file can complicate reviews. |
| **When** | Editing one layout constantly conflicts with another, or the file becomes hard to navigate. |
| **Risk** | Low if imports stay shallow and public entry points (`render_panel_view` or equivalent) stay stable. |

---

## 3. `app/display_idotmatrix_api_client.py` — transport vs payload

| | |
|--|--|
| **Idea** | Separate **BLE / asyncio / library calls** from **PNG/RGB preparation** (DIY snap, dimensions) so “what bytes go up” is testable without a device. |
| **Why** | The file mixes async thread management, hardware quirks, and image pipeline. |
| **When** | Adding another display backend, or debugging upload vs rendering becomes frequent. |
| **Risk** | Medium: threading and async boundaries are easy to get wrong; keep integration tests or manual smoke checklist for real hardware. |

---

## 4. `app/config.py` — structured settings (e.g. pydantic-settings)

| | |
|--|--|
| **Idea** | Replace hand-rolled `from_env()` with **`pydantic-settings`** (or similar) for typed fields, validation, and clearer error messages on bad `.env` values. |
| **Why** | Large `Settings` dataclass + many `_env_*` helpers are correct but verbose; validation is mostly implicit. |
| **When** | Misconfiguration in production hurts often enough to justify a new dependency and migration effort. |
| **Risk** | Low for behavior if defaults match exactly; watch for subtle string/bool parsing differences. |

---

## 5. Documentation paths (cosmetic)

| | |
|--|--|
| **Idea** | Pick one canonical location for onboarding copy: e.g. only **`docs/specs/SPECS_ONBOARDING.md`** locally, plus **`docs/PRODUCTION.md`** as the always-cloned source of truth for runtime. |
| **Why** | Older text mentioned `docs/SPECS_ONBOARDING.md` or `docs/specs/README.md` as alternatives; reduces “which file did I edit?” |
| **When** | Next time you reorganize docs. |

---

## Verification

After any refactor touching behavior:

```bash
source .venv/bin/activate   # or your venv
pytest
```

On a Pi or with hardware, do a short **smoke run** (`python -m app.main`) if BLE or display code moved.

---

## Related

- **[`PRODUCTION.md`](PRODUCTION.md)** — architecture, modules, env vars, deployment.
- **Local `docs/specs/`** — pixel layout and v3 design detail (gitignored); see **`SPECS_ONBOARDING.md`** if you keep a copy there.
