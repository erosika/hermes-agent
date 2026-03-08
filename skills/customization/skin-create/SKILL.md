---
name: skin-create
description: Design and install a custom named color skin for the Hermes terminal UI. Generates the full prompt_toolkit CSS class mapping, patches cli.py to register the new skin, and activates it via /skin <name>.
version: 1.0.0
author: Hermes Agent
license: MIT
dependencies: []
metadata:
  hermes:
    tags: [skin, theme, color, terminal, UI, prompt_toolkit, customization, design]
    related_skills: []

---

# Skin Create Skill

Design and install a new named color skin for the Hermes terminal. Skins are applied at runtime via `/skin <name>` with no restart required.

## How Skins Work

Hermes uses `prompt_toolkit` for its TUI. Skins are Python dicts mapping CSS class names to color strings, stored in `_SKIN_THEMES` in `cli.py` (around line 419). The active skin is swapped at runtime via `app.style = PTStyle.from_dict(...)` and persisted to `~/.hermes/config.yaml` under `display.skin`.

## Step 1: Design the Palette

Before mapping classes, establish 4-6 semantic color roles. Good skins have:

| Role | Purpose |
|------|---------|
| `fg-primary` | Main readable text in inputs and boxes |
| `fg-muted` | Hints, placeholders, secondary text |
| `accent` | Borders, rules, interactive highlights |
| `accent-bright` | Selected items, titles, emphasis |
| `alert` | Sudo/danger prompts (should be visually distinct) |
| `bg-menu` | Completion menu background |
| `bg-menu-selected` | Selected completion entry background |

Then assign hex values. All colors must be valid CSS hex: `#rrggbb` or `#rgb`.

### Palette Format

```
fg-primary:        #e6edf3
fg-muted:          #4b5563
accent:            #4169e1
accent-bright:     #7eb8f6
alert:             #f7a072
bg-menu:           #0b0e14
bg-menu-selected:  #1a2233
```

## Step 2: Map the 29 CSS Class Keys

Every skin **must** define all 29 keys. The value is a prompt_toolkit style string:
- Foreground only: `#rrggbb`
- Foreground + modifier: `#rrggbb bold` or `#rrggbb italic`
- Background + foreground: `bg:#rrggbb #rrggbb`
- Background + foreground + modifier: `bg:#rrggbb #rrggbb bold`

### Key Reference

| Key | Styled element |
|-----|---------------|
| `input-area` | Text typed in the main input field |
| `placeholder` | Placeholder text when input is empty |
| `prompt` | The `❯` prompt prefix (idle state) |
| `prompt-working` | The `❯` prompt prefix (agent running) |
| `hint` | Hint text beneath the input (keyboard shortcuts, status) |
| `input-rule` | The horizontal rule above the input area |
| `image-badge` | Badge label shown when an image is attached |
| `completion-menu` | Completion dropdown base (bg + fg) |
| `completion-menu.completion` | Individual completion entry |
| `completion-menu.completion.current` | Highlighted/selected completion entry |
| `completion-menu.meta.completion` | Meta description text per entry |
| `completion-menu.meta.completion.current` | Meta text for selected entry |
| `clarify-border` | Box-drawing characters of clarify dialog |
| `clarify-title` | Title text inside clarify dialog header |
| `clarify-question` | Question text inside clarify dialog |
| `clarify-choice` | Unselected choice option |
| `clarify-selected` | Selected choice option (`> item`) |
| `clarify-active-other` | "Other (type below)" active state |
| `clarify-countdown` | Countdown timer text |
| `sudo-prompt` | The `⚿ ❯` prefix in sudo/password mode |
| `sudo-border` | Box-drawing characters of sudo dialog |
| `sudo-title` | Title text inside sudo dialog header |
| `sudo-text` | Body text inside sudo dialog |
| `approval-border` | Box-drawing characters of approval dialog |
| `approval-title` | Title text inside approval dialog header |
| `approval-desc` | Description text inside approval dialog |
| `approval-cmd` | Command/action text inside approval dialog |
| `approval-choice` | Unselected approval option |
| `approval-selected` | Selected approval option (`> item`) |

**Total: 29 keys** (the schema grew — always copy the full `default` block and modify values, never omit keys).

## Step 3: Generate the Skin Dict

Produce a Python dict literal with all 29 keys. Example (a night-sea theme):

```python
"nightsea": {
    "input-area": "#b8d4e8",
    "placeholder": "#3a5068 italic",
    "prompt": "#7ec8e3",
    "prompt-working": "#3a5068 italic",
    "hint": "#3a5068 italic",
    "input-rule": "#1b6ca8",
    "image-badge": "#7ec8e3 bold",
    "completion-menu": "bg:#0a1520 #b8d4e8",
    "completion-menu.completion": "bg:#0a1520 #b8d4e8",
    "completion-menu.completion.current": "bg:#0d2035 #7ec8e3",
    "completion-menu.meta.completion": "bg:#0a1520 #3a5068",
    "completion-menu.meta.completion.current": "bg:#0d2035 #7ec8e3",
    "clarify-border": "#1b6ca8",
    "clarify-title": "#7ec8e3 bold",
    "clarify-question": "#b8d4e8",
    "clarify-choice": "#3a5068",
    "clarify-selected": "#7ec8e3 bold",
    "clarify-active-other": "#a0c8e0 italic",
    "clarify-countdown": "#1b6ca8",
    "sudo-prompt": "#63d0a6 bold",
    "sudo-border": "#1b6ca8",
    "sudo-title": "#63d0a6 bold",
    "sudo-text": "#b8d4e8",
    "approval-border": "#1b6ca8",
    "approval-title": "#f7a072 bold",
    "approval-desc": "#b8d4e8 bold",
    "approval-cmd": "#3a5068 italic",
    "approval-choice": "#3a5068",
    "approval-selected": "#7ec8e3 bold",
},
```

## Step 4: Patch cli.py

Run this Python script to inject the new skin into `_SKIN_THEMES`:

```python
#!/usr/bin/env python3
"""
Usage: python3 install_skin.py
Injects a new skin into hermes-agent/cli.py.
Edit SKIN_NAME and SKIN_DICT before running.
"""
import re
import sys
from pathlib import Path

CLI_PATH = Path(__file__).parent.parent.parent / "cli.py"  # adjust if run from elsewhere

SKIN_NAME = "nightsea"  # <- change this

SKIN_DICT = '''    "nightsea": {
        "input-area": "#b8d4e8",
        "placeholder": "#3a5068 italic",
        "prompt": "#7ec8e3",
        "prompt-working": "#3a5068 italic",
        "hint": "#3a5068 italic",
        "input-rule": "#1b6ca8",
        "image-badge": "#7ec8e3 bold",
        "completion-menu": "bg:#0a1520 #b8d4e8",
        "completion-menu.completion": "bg:#0a1520 #b8d4e8",
        "completion-menu.completion.current": "bg:#0d2035 #7ec8e3",
        "completion-menu.meta.completion": "bg:#0a1520 #3a5068",
        "completion-menu.meta.completion.current": "bg:#0d2035 #7ec8e3",
        "clarify-border": "#1b6ca8",
        "clarify-title": "#7ec8e3 bold",
        "clarify-question": "#b8d4e8",
        "clarify-choice": "#3a5068",
        "clarify-selected": "#7ec8e3 bold",
        "clarify-active-other": "#a0c8e0 italic",
        "clarify-countdown": "#1b6ca8",
        "sudo-prompt": "#63d0a6 bold",
        "sudo-border": "#1b6ca8",
        "sudo-title": "#63d0a6 bold",
        "sudo-text": "#b8d4e8",
        "approval-border": "#1b6ca8",
        "approval-title": "#f7a072 bold",
        "approval-desc": "#b8d4e8 bold",
        "approval-cmd": "#3a5068 italic",
        "approval-choice": "#3a5068",
        "approval-selected": "#7ec8e3 bold",
    },'''  # <- replace with your skin dict

src = CLI_PATH.read_text()

# Guard: already installed?
if f'"{SKIN_NAME}"' in src:
    print(f"Skin '{SKIN_NAME}' already exists in {CLI_PATH}. Aborting.")
    sys.exit(1)

# Find the closing brace of _SKIN_THEMES and insert before it
# The dict ends with the last skin's closing brace followed by a lone }
pattern = r'(_SKIN_THEMES: Dict\[str, Dict\[str, str\]\] = \{.*?)(^\})'
match = re.search(pattern, src, re.DOTALL | re.MULTILINE)

if not match:
    print("Could not locate _SKIN_THEMES closing brace. Manual insertion required.")
    sys.exit(1)

insert_pos = match.start(2)
new_src = src[:insert_pos] + SKIN_DICT + "\n" + src[insert_pos:]

CLI_PATH.write_text(new_src)
print(f"Skin '{SKIN_NAME}' installed. Run /skin {SKIN_NAME} to activate.")
```

Place this script anywhere (e.g. `/tmp/install_skin.py`) and run it with `python3 /tmp/install_skin.py`.

## Step 5: Activate

After patching, Hermes must be restarted once for the new entry to load into memory. Then:

```
/skin nightsea
```

The skin is applied immediately at runtime and saved to `~/.hermes/config.yaml` so it persists across restarts.

## Design Tips

- **Legibility first.** `input-area` is the most-read text — choose a color that reads comfortably against the terminal background.
- **Border contrast.** `*-border` colors should have at least 30% luminance difference from the terminal background so box-drawing characters are visible.
- **Alert differentiation.** `sudo-prompt` and `sudo-title` should be visually distinct from `clarify-*` and `approval-*`. A warm hue (orange, coral, amber) for approval vs cool (teal, mint) for sudo reads naturally as "action needed" vs "identity verification".
- **Muted text at 40-50% brightness.** `placeholder`, `hint`, `*-choice`, `*-cmd`, `clarify-countdown` should be clearly secondary without disappearing.
- **Completion menu**: `bg-menu` should be darker than the terminal default. `completion.current` bg should be distinctly lighter than `completion` bg.
- **No gradients, no bright white (#ffffff) as primary.** Use off-white or tinted light colors for primary fg.

## Validation Checklist

- [ ] All 29 keys present
- [ ] All hex values valid (`#rrggbb` format, no shorthand `#rgb` in bg: positions)
- [ ] `completion-menu` and `completion-menu.completion` use `bg:#... #...` format
- [ ] `prompt-working` is visibly muted relative to `prompt`
- [ ] `sudo-prompt` is visually distinct from `clarify-selected` and `approval-selected`
- [ ] `*-border` reads at normal terminal width (test at 80 and 120 columns)

## Decision Flow

1. **User names a theme** ("ocean", "sakura", "obsidian") → derive palette from the name's visual semantics
2. **Establish 5-6 palette roles** → map to semantic groups
3. **Fill all 29 keys** from the palette, using `bold`/`italic` modifiers for hierarchy
4. **Run install script** → verify no parse error
5. **Restart Hermes** → `/skin <name>` → test all dialogs (clarify, sudo, approval)
6. **Iterate** if any dialog reads poorly at narrow widths or in ambient light conditions
