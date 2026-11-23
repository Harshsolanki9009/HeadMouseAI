# Jadoo Ink Wash Design System

> **Official Design Specification & Visual Standards for HeadMouseAI + Jadoo Desktop Accessibility System.**  
> Target Profile: Windows 10/11 x64, Desktop Accessibility, Intel Core i3-6100, High Contrast & Low-Latency UI.

---

## 1. Aesthetic Philosophy: The Ink Wash Standard

The **Ink Wash** design system replaces conventional heavy dark modes and hyper-saturated accents with a minimalist, disciplined monochrome aesthetic rooted in East Asian sumi-e ink wash painting and precision German industrial design.

Rather than relying on intense neon glows or distracting drop shadows, Jadoo emphasizes:
- **Restrained Value Hierarchy**: Rich layered values of charcoal, graphite, cool gray, and silver gray.
- **Whisper Accents**: Minimal, purposeful semantic indicators (Sage Gray for active/success, Muted Amber for caution/dictation, Muted Crimson for emergency stops).
- **Extreme Contrast Clarity**: Soft ivory on charcoal exceeding **13:1 WCAG contrast ratio**, ensuring effortless legibility in daylight or dark environments.
- **Tactile Accessibility**: Substantial 44px minimum click targets for nose cursor and eye-wink targeting, accompanied by unmistakable 2px focus outlines.

---

## 2. Design Tokens

### Color Palette

| Token Name | Hex Code | Semantic Role | Contrast vs Canvas |
|---|---|---|---|
| `INK_CANVAS` | `#17191C` | Primary application canvas / viewport background | — |
| `INK_GRAPHITE` | `#222529` | Container, panel, and card background | 1.15:1 |
| `INK_ELEVATED` | `#2D3137` | Hovered surfaces, selected tab headers, elevated cards | 1.35:1 |
| `INK_COOL_GRAY` | `#34383D` | Primary card borders, dividers, subtle separators | 1.6:1 |
| `INK_MUTED_SLATE` | `#777F87` | Inactive icon fills, secondary borders, disabled text | 3.8:1 |
| `INK_SILVER_GRAY` | `#B9C0C7` | Secondary body text, sub-labels, telemetry metrics | 7.8:1 (WCAG AAA) |
| `INK_SOFT_IVORY` | `#F2F0EA` | Primary headings, active values, high-contrast labels | 13.5:1 (WCAG AAA) |
| `INK_SAGE_GRAY` | `#89958C` | Active status, speech recognition listening, ready state | 5.2:1 (WCAG AA) |
| `INK_MUTED_AMBER` | `#C19A62` | Active dictation recording, attention, pending calibration | 6.1:1 (WCAG AA) |
| `INK_MUTED_CRIMSON` | `#B66F70` | F9 emergency stop, tracking halted, error states | 4.8:1 (WCAG AA) |
| `INK_PURE_WHITE` | `#FFFFFF` | Focus rings, primary button active highlights | 14.8:1 (WCAG AAA) |
| `INK_PURE_BLACK` | `#0D0E10` | Primary action button text (on soft ivory surface) | >15:1 |

### Typography

| Category | Font Family | Size | Weight | Line Height |
|---|---|---|---|---|
| Display / Brand | `Segoe UI Variable Display`, `Segoe UI`, sans-serif | 20px – 28px | 700 Bold | 1.2 |
| Section Headings | `Segoe UI Variable Text`, `Segoe UI`, sans-serif | 14px – 16px | 700 Bold | 1.3 |
| Body / Primary Text | `Segoe UI Variable Text`, `Segoe UI`, sans-serif | 12px – 13px | 500 / 600 | 1.4 |
| Captions / Badges | `Segoe UI Variable Text`, `Segoe UI`, sans-serif | 10px – 11px | 700 Bold | 1.2 |
| Tabular / Telemetry | `Cascadia Code`, `Consolas`, monospace | 11px – 12px | 600 SemiBold | 1.3 |

### Geometry & Spacing Scale

- **Radius**:
  - `RADIUS_SM`: `4px` (Badges, tags, small pills)
  - `RADIUS_MD`: `6px` – `8px` (Buttons, input boxes, dropdowns)
  - `RADIUS_LG`: `10px` – `12px` (Cards, floating panels, dialog windows)
  - `RADIUS_ROUND`: `9999px` (Full circle indicators, avatar nodes)
- **Grid Margins**: Base 4px scale (`4px`, `8px`, `12px`, `16px`, `24px`).
- **Touch / Head Target Minimum**: `44px` height by `44px` width for all actionable accessibility controls.

---

## 3. High-Resolution Vector SVG Graphics Catalog

Located in `assets/graphics/`:

1. `jadoo_logo.svg` (120x120):
   - *Composition*: Dual ink-wash concentric orbital rings, precision aperture eye arc, central AI iris node, and 4 cardinal calibration crosshairs.
   - *Use*: Application identity, splash screen, and title bar.
2. `ink_wash_abstract.svg` (800x400):
   - *Composition*: Flowing organic ink clouds (`sumi-e`), subtle strata contours, and constellation points.
   - *Use*: Background watermark for cards, modals, and landing banners.
3. `voice_waveform.svg` (480x120):
   - *Composition*: 33 balanced vector waveform bars with ink gradient fills, peaking at center white speech impulse.
   - *Use*: Voice Engine panel visualizer and audio diagnostic representation.
4. `ai_cursor_art.svg` (320x320):
   - *Composition*: Wireframe facial landmark mesh, calibrated reticle, nose-tip landmark (#4) crosshair, and virtual raycast cursor beam.
   - *Use*: AI Cursor tab, settings card, and calibration instructions.
5. `task_workflow_art.svg` (600x240):
   - *Composition*: 4-stage pipeline nodes (`Intent` -> `Observe UIA` -> `Plan Gemini` -> `Act & Verify Vercel agent-desktop`).
   - *Use*: Autonomous Task Agent card and workflow documentation.
6. `empty_state.svg` (280x200):
   - *Composition*: Concentric ripples, minimal clipboard outline, and ready status sparkle.
   - *Use*: Empty task queue, zero-history logs, and standby views.
7. `welcome_art.svg` (640x200):
   - *Composition*: Full-width branded onboarding banner with capability badges (`Nose Cursor`, `Cloud Whisper`, `agent-desktop`) and focal aperture ring.
   - *Use*: First-launch onboarding modal and Help reference tab.

---

## 4. Motion Design & Accessibility Standards

### 1. Motion Budget for Low-End Hardware
- All active animations (such as the dictation breathing visualizer) are capped at **20 FPS (50ms interval)** via `QTimer`, consuming <0.2% CPU on Intel Core i3-6100.
- No continuous CPU-intensive software blurs or expensive CSS shadow repaints in live loops.
- Live tracking telemetry updates use selective widget repaints and cached stylesheet comparisons to prevent layout jitter.

### 2. "Reduce Motion" Support
- When `reduce_motion: true` is toggled in user settings:
  - Breathing oscillation loops are immediately deactivated.
  - State changes transition instantaneously with crisp solid borders.
  - Dialog entrance animations switch from sliding/fading to direct paint.

### 3. Keyboard & Switch Navigation
- Every interactive element features a prominent `2px solid #F2F0EA` focus outline.
- Tabbing order is logical and cycle-safe across all cards.
- Global hardware shortcuts (`F8` for mouse actuation toggle, `F9` for Emergency Stop, `Ctrl+Shift+D` for voice dictation) operate at the system level regardless of UI focus.
