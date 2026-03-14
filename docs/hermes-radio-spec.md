# hermes-radio

**CLI pirate radio player for Hermes Agent. Crate-digging across decades and borders, with AI mic breaks between the cuts.**

- Repo: nousresearch/hermes-agent
- Stack: Python + mpv
- Date: 2026-03-14

---

## Contents

1. [Vision](#vision)
2. [Prior Art](#prior-art)
3. [Architecture](#architecture)
4. [Music Sources](#music-sources)
5. [Audio Playback Engine](#audio-playback-engine)
6. [TTS Mic Breaks](#tts-mic-breaks)
7. [Pirate Radio Channels](#pirate-radio-channels)
8. [Terminal Interface](#terminal-interface)
9. [Hermes Integration](#hermes-integration)
10. [Configuration](#configuration)
11. [Implementation Plan](#implementation-plan)
12. [Open Decisions](#open-decisions)

---

## Vision

A CLI radio player that lives inside Hermes Agent, combining cliamp's terminal-native playback with Acephale Radio's crate-digging intelligence. The player pulls music from Radiooooo's 1900--2020 global archive, tunes into pirate radio streams from around the world, and punctuates the listening experience with AI-generated mic breaks -- station IDs, track commentary, time checks, and DJ banter synthesized through Hermes' existing TTS infrastructure.

This is not a background service or a streaming server. It is a **local CLI player** that occupies your terminal like cliamp does, controlled by the agent or by keyboard. Think of it as giving Hermes a radio dial and a microphone.

> **Core thesis** -- Radiooooo's API delivers curated tracks by decade, country, and mood with zero authentication. Radio Browser indexes 45,000+ live streams. Hermes already has TTS. mpv handles all codecs and protocols via JSON IPC. The pieces exist; this spec connects them.

### What it is not

- Not an Icecast/Liquidsoap broadcast server (that's Acephale Radio)
- Not a Go rewrite of cliamp (we take UI inspiration, not the codebase)
- Not a standalone application (it's a Hermes tool/skill that can also run independently)

---

## Prior Art

### cliamp

Go-based terminal music player (814 stars, MIT). Bubbletea TUI with spectrum visualizer, 10-band EQ, gapless playback. Plays local files, Icecast/SHOUTcast streams, YouTube, SoundCloud, Bandcamp, Spotify, Navidrome. Audio pipeline: decode -> resample -> gapless mux -> biquad EQ -> volume -> FFT tap -> speaker. Key ideas to borrow:

- Full-screen alt-screen TUI with now-playing, progress bar, visualizer, keybindings overlay
- ICY metadata extraction from Icecast streams (in-band artist/title)
- Custom radio stations via `~/.config/cliamp/radios.toml`
- Theme engine with TOML-based color schemes
- Auto-reconnect with exponential backoff for streams

### Acephale Radio

Autonomous multi-channel AI radio station (erosika/acephale, MIT). Bun + TypeScript, four stations with distinct AI personalities streaming through Liquidsoap -> Icecast. Key ideas to absorb:

- **Radiooooo client** -- fully working TypeScript port of the radio5 Ruby gem. `POST /play` with `{mode, isocodes, decades, moods}` returns signed CDN URLs to MP3/OGG tracks. No auth required.
- **Decade/mood/country weighting** -- Crate Digger's weighted decade picker favoring 60s--80s, mood bias toward slow/weird, country discovery via `/country/mood?decade=X`
- **DJ commentary pipeline** -- LLM generates commentary -> TTS renders it -> ffmpeg mixes voice over music with volume ducking (voice 1.2x, music 0.4x) -> queued to stream
- **Track metadata tagging** -- ffmpeg remux to embed title/artist/album before playback
- **Honcho memory** -- persistent per-station sessions, each dig saved as a message pair (commentary + "Played: title by artist")

### Cosmania DJ Agent

Single-station DJ agent in the Cosmania framework. Runs every 30 minutes via cron, pulls from Radiooooo, generates commentary via Mistral, uses ElevenLabs for voice. Same Icecast/Liquidsoap infrastructure. Budget-aware ($2/day). Validates that the Radiooooo -> LLM -> TTS -> stream pipeline works in a scheduled autonomous loop.

**Acephale Radio vs. Hermes Radio:**

| Aspect | Acephale Radio | Hermes Radio (this spec) |
|---|---|---|
| Model | Server-side broadcast (Icecast) | Local CLI playback (mpv) |
| Channels | Multiple concurrent stations | Single stream, switchable |
| Language | Bun/TypeScript | Python (Hermes native) |
| TTS | Gemini TTS (Chirp 3 HD) | Edge/ElevenLabs/OpenAI TTS |
| Infra | Docker (Icecast + Liquidsoap) | No infrastructure, just mpv |
| UI | Rotary dial web UI | Terminal TUI (rich/textual) |

---

## Architecture

```
SOURCES                          ENGINE                    INTERFACE
+------------------+         +----------------+       +---------------+
| Radiooooo API    |-------->| Track Queue    |       | Terminal TUI  |
| (decade/country) |         | (playlist)     |       | (now playing, |
+------------------+         +-------+--------+       |  visualizer)  |
                                     |                +-------+-------+
+------------------+         +-------v--------+              |
| Radio Browser    |-------->| mpv            |<-------------+
| (45k+ streams)   |         | (JSON IPC)     |       Keyboard Controls
+------------------+         +-------+--------+
                                     ^
+------------------+         +-------+--------+
| Radio Garden     |-------->| Voice mpv      |
| (geographic)     |         | (TTS playback) |
+------------------+         +-------+--------+
                                     ^
+------------------+                 |
| SomaFM           |---------+      |
| (curated)        |         |      |
+------------------+         |      |
                             |      |
+------------------+    +----v------+---+
| Local Files      |    | TTS Engine    |
+------------------+    | (Edge/11Labs) |
                        +-------+-------+
                                ^
                        +-------+-------+
                        | LLM Commentary|
                        | + Session Mem |
                        +---------------+
```

### Two operational modes

**Autonomous mode (Hermes tool):** The agent invokes `radio_play`, `radio_tune`, `radio_skip`, `radio_mic_break` tools during conversation. Music plays in the background while the user works. The agent decides when to insert mic breaks based on track transitions, time elapsed, or user requests. Playback state is visible in the Hermes CLI status line.

**Interactive mode (standalone TUI):** Full-screen terminal interface launched via `hermes radio` CLI subcommand. Keyboard-driven: tune between sources, skip tracks, adjust volume, toggle mic breaks. The TUI takes over the terminal like cliamp does. Can still receive agent commands via the tool interface.

### Dual-mpv pattern

Two mpv instances running simultaneously, communicating via separate JSON IPC sockets:

- **Primary instance** (`/tmp/hermes-radio-main.sock`) -- music/stream playback
- **Voice instance** (`/tmp/hermes-radio-voice.sock`) -- TTS mic break playback

During a mic break: primary volume ducks to 30% -> voice instance plays the TTS clip -> primary volume restores. This avoids dropping the stream connection (critical for live radio) and eliminates the need for ffmpeg mixing at playback time.

---

## Music Sources

### Radiooooo (curated tracks)

The heart of the crate-digging experience. Port the working client from Acephale Radio to Python.

| Endpoint | Method | Purpose |
|---|---|---|
| `POST /play` | POST | Random track by decade/country/mood. Body: `{"mode":"explore","isocodes":["FRA"],"decades":[1960],"moods":["SLOW"]}` |
| `GET /track/play/{id}` | GET | Fetch specific track by ID |
| `POST /play` | POST | Island/playlist tracks. Body: `{"mode":"islands","island":"id","moods":[...]}` |
| `GET /country/mood?decade=X` | GET | Countries with content for a given decade, grouped by mood |
| `GET /island/all` | GET | All themed islands/playlists |

Track responses include time-limited signed URLs to MP3 and OGG files on `asset.radiooooo.com`. No authentication required. The client should pre-fetch the next track while the current one plays (Acephale's pattern), falling back gracefully on 404s.

> **Decade weighting from Acephale** -- Crate Digger uses: 1970s (highest), 1960s/1980s (high), 1950s/1990s (medium), 2000s/1940s (low), 1930s/2010s/2020s (lower), 1900s/1910s/1920s (rare). This creates a natural bell curve around the golden era of recorded music. Configurable per-profile.

### Radio Browser (live streams)

Open directory of 45,000+ radio stations at `all.api.radio-browser.info`. JSON API, no auth, excellent search.

| Endpoint | Purpose |
|---|---|
| `GET /json/stations/search?name=X&tag=X&country=X` | Search stations by name, tag, country, codec, bitrate |
| `GET /json/stations/topclick` | Most popular stations |
| `GET /json/stations/topvote` | Highest rated stations |
| `GET /json/stations/lastchange` | Recently updated stations |
| `GET /json/url/{uuid}` | Resolve station UUID to direct stream URL |
| `GET /json/tags` | All tags with station counts |
| `GET /json/countries` | All countries with station counts |

### Radio Garden (geographic discovery)

3D globe of live radio worldwide. API at `radio.garden/api`, no auth. The key endpoint is `GET /ara/content/listen/{channelId}/channel.mp3` which returns a 302 redirect to the actual Icecast/SHOUTcast stream. Region restrictions are client-side only.

| Endpoint | Purpose |
|---|---|
| `GET /ara/content/places` | All places with radio (~30k entries, 1.4MB). Geo coords as `[lon, lat]` |
| `GET /ara/content/page/{placeId}` | Place details with station list |
| `GET /ara/content/channel/{channelId}` | Station details |
| `GET /search?q={query}` | Search places, countries, stations |
| `GET /ara/content/listen/{channelId}/channel.mp3` | 302 redirect to live stream |

### SomaFM (curated underground)

~40 curated channels. `GET https://api.somafm.com/channels.json` returns all channels with stream URLs, genres, listeners, DJ info. Zero auth. Channels like `defcon`, `darkzone`, `sf1033`, `vaporwaves`, `dronezone`, `deepspaceone` fit the pirate radio aesthetic. Direct MP3/AAC stream URLs.

### Custom stations

User-defined stations in config, following cliamp's TOML pattern. Any direct stream URL (Icecast, SHOUTcast, HTTP MP3/OGG/AAC) or M3U/PLS playlist URL.

### Local files

Pass directories or globs. mpv handles all common formats natively (MP3, FLAC, OGG, WAV, M4A, AAC, Opus, WMA, WebM). Recursive directory scanning.

---

## Audio Playback Engine

### Why mpv

- Handles every codec and protocol (HTTP, HTTPS, Icecast, SHOUTcast, local files, RTSP, HLS)
- JSON IPC socket (`--input-ipc-server`) provides full programmatic control
- ICY metadata extraction built in (artist/title from Icecast streams)
- Gapless playback via playlist mode
- Volume control, seeking, pause/resume, playlist manipulation, all via IPC
- Available on all platforms: `brew install mpv` / `apt install mpv` / `choco install mpv`
- Minimal resource usage, no GUI required (`--no-video --no-terminal`)

### IPC control protocol

Communication via Unix domain socket. Send JSON commands, receive JSON responses and events.

```bash
# Start mpv with IPC socket
mpv --idle --no-video --no-terminal \
    --input-ipc-server=/tmp/hermes-radio-main.sock

# Python client sends JSON commands over the socket
{"command": ["loadfile", "https://stream.url"]}
{"command": ["set_property", "volume", 70]}
{"command": ["set_property", "pause", true]}
{"command": ["get_property", "media-title"]}
{"command": ["observe_property", 1, "metadata"]}

# mpv sends events back (metadata changes, track ends, etc.)
{"event": "metadata-update"}
{"event": "end-file", "reason": "eof"}
```

### Python mpv wrapper

Thin wrapper class managing the mpv subprocess + socket connection. Not using `python-mpv` (libmpv bindings, heavy) or `node-mpv` (wrong language). Instead, a lightweight custom client (~200 lines) that:

- Spawns mpv as a subprocess with the IPC socket
- Connects via `asyncio` Unix socket
- Sends commands as newline-delimited JSON
- Parses responses and events asynchronously
- Emits callbacks on metadata change, track end, playback error
- Handles auto-reconnect if mpv crashes

### Playback modes

| Mode | Source | Behavior |
|---|---|---|
| Crate dig | Radiooooo | Track-by-track. Pre-fetch next track while current plays. Gapless transition. Mic break between tracks. |
| Live radio | Radio Browser / Radio Garden / SomaFM / custom | Continuous stream. ICY metadata updates. Mic break on metadata change (new song detected). |
| Local | Files/directories | Sequential or shuffle. Gapless. Mic break between tracks. |

---

## TTS Mic Breaks

The signature feature. AI-generated DJ interjections between tracks or during stream metadata changes, delivered through Hermes' existing TTS tool.

### Mic break types

| Type | Trigger | Content | Duration |
|---|---|---|---|
| Track intro | New track starts (crate dig mode) | Artist/title, decade, country, mood commentary | 5--15s |
| Station ID | Every N tracks or N minutes | "You're listening to Hermes Radio" + time + station context | 3--8s |
| Stream update | ICY metadata change (live radio) | Announce new song on the live stream | 3--8s |
| Crate commentary | Between tracks (crate dig) | Deep-cut context: "This 1967 Senegalese psych-folk 45 was only pressed in a run of 200..." | 10--25s |
| Mood shift | After N tracks or manual trigger | Transitional patter when the mood/decade shifts | 5--12s |
| Sign-off | Player quit | Closing farewell with session summary | 5--10s |

### Generation pipeline

```
Track transition     Build context         LLM generates
or timer trigger --> (track metadata,  --> DJ script
                     listening history,    (1-3 sentences)
                     time of day)
                                                |
                                                v
Restore primary      Play TTS clip        TTS renders
volume to 100%   <-- on voice mpv     <-- to audio file
over 500ms           instance             (Edge/ElevenLabs/OpenAI)
                          ^
                          |
                     Duck primary volume
                     to 30% over 500ms
```

### Volume ducking

Smooth volume transitions via mpv IPC. The primary instance volume ramps from 100% -> 30% over 500ms (10 steps at 50ms intervals), the voice clip plays, then 30% -> 100% ramp over 500ms. If the user skips during a mic break, the voice instance stops immediately and the primary volume snaps back.

### Commentary generation

The LLM prompt for mic break commentary receives:

- Current track metadata (title, artist, decade, country, mood)
- Previous 3--5 tracks played (for continuity)
- Current time of day (morning/afternoon/evening/late night affects tone)
- Current source mode (crate dig vs. live radio vs. local)
- Station persona (configurable: deadpan, enthusiastic, conspiratorial, encyclopedic)

Prompt instructs: 1--3 sentences, conversational, no hashtags, no emojis, never mention being an AI. Output is plain text sent directly to the TTS tool.

### TTS provider selection

Reuses Hermes' existing `tools/tts_tool.py` infrastructure. Provider configured in `~/.hermes/config.yaml` under `tts:`. Supports Edge TTS (free, no key), ElevenLabs (premium, voice cloning), OpenAI TTS. The radio player doesn't add new TTS code; it calls the existing tool function.

> **Latency consideration** -- Edge TTS is ~1--2s for short clips. ElevenLabs is ~2--4s. To avoid dead air, the mic break pipeline should **pre-generate** the next mic break while the current track plays, not wait for the track to end. Cache the rendered audio in `~/.hermes/audio_cache/radio/`.

---

## Pirate Radio Channels

The player ships with a curated set of pirate/underground/indie radio presets and provides tools to discover more.

### Built-in presets

| Source | Preset Channels | Discovery Method |
|---|---|---|
| SomaFM | `defcon`, `darkzone`, `sf1033`, `vaporwaves`, `dronezone`, `deepspaceone`, `secretagent`, `lush`, `cliqhop` | `api.somafm.com/channels.json` |
| Radio Browser | Tags: `pirate`, `underground`, `experimental`, `freeform`, `college` | Search by tag |
| Radio Garden | User-discovered stations saved by place | Geographic + search |
| Custom | User-added stream URLs | Config file |

### Channel discovery commands

```bash
# Browse by tag
hermes radio search "experimental electronic"

# Browse by location (Radio Garden)
hermes radio explore "Tokyo"
hermes radio explore "Lagos"

# Browse SomaFM channels
hermes radio soma

# Browse Radiooooo by decade + country
hermes radio crate --decade 1970 --country JPN --mood weird

# Save current stream as a preset
hermes radio save "my-station-name"

# List saved presets
hermes radio presets
```

### Tuning model

In the TUI, channels are organized as a flat dial (inspired by Acephale's rotary interface, but linearized for terminal). Left/right arrow keys move between presets. The current position persists across sessions. Channels are grouped by source type with visual separators.

---

## Terminal Interface

### Layout (standalone mode)

```
+-------------------------------------------------------+
| HERMES RADIO                      23:47  vol 85       |
|                                                       |
|  Khruangbin - Maria Tambien                           |
|  1970s  THA  slow                     2:34 / 4:12     |
|  ===========================-----------               |
|                                                       |
|  |||| ||| |||| | ||||| || ||| |||| ||| |              |
|  |||| ||| |||| | ||||| || ||| |||| ||| |              |
|                                                       |
|  DIAL: [soma:defcon] [crate:1970/JPN] [custom:nts]    |
|                                                       |
|  q quit  space pause  n skip  m mic  +/- vol          |
+-------------------------------------------------------+
```

### Components

- **Header bar** -- station name, clock, volume indicator
- **Now playing** -- track title + artist (scrolling if long), decade/country/mood tags for Radiooooo tracks
- **Progress bar** -- for finite tracks (Radiooooo, local). Hidden for live streams. Unicode block characters.
- **Spectrum visualizer** -- optional FFT visualization. mpv can output audio levels via the `af=lavfi=astats` filter or via the `ao-volume` property. Simplified bar display (8--12 bands). Can be toggled off.
- **Channel dial** -- horizontal strip showing adjacent presets with the active one highlighted
- **Keybindings bar** -- contextual hints at the bottom

### Keybindings

| Key | Action |
|---|---|
| `space` | Play / pause |
| `n` | Next track / skip |
| `p` | Previous track (crate/local mode) |
| `+` / `-` | Volume up / down (5% steps) |
| `left` / `right` | Previous / next channel on dial |
| `m` | Trigger mic break now |
| `M` | Toggle auto mic breaks on/off |
| `v` | Toggle visualizer |
| `i` | Show track info overlay |
| `s` | Save current channel as preset |
| `/` | Search stations |
| `q` | Quit (with sign-off mic break if enabled) |

### Implementation

Use `rich` (already a Hermes dependency) for rendering. The TUI runs in an alt-screen context (`rich.console.Console()` with `screen=True`). Input handling via Python's `curses` or `prompt_toolkit` (also already a Hermes dependency) for non-blocking key capture. The rendering loop polls mpv for state changes (metadata, position, volume) every 200ms.

---

## Hermes Integration

### Tool registration

New tools registered in `tools/radio_tool.py`, following the existing registry pattern:

| Tool | Parameters | Description |
|---|---|---|
| `radio_play` | `source`, `query` | Start playing. Source: "crate" (Radiooooo), "stream" (Radio Browser/Garden/SomaFM), "local" (files). Query: search terms, decade/country/mood for crate, stream URL for direct. |
| `radio_tune` | `channel` | Switch to a preset channel by name |
| `radio_skip` | -- | Skip current track |
| `radio_stop` | -- | Stop playback, kill mpv instances |
| `radio_status` | -- | Return current playback state (track, source, volume, position) |
| `radio_volume` | `level` | Set volume (0--100) |
| `radio_mic_break` | `text` (optional) | Trigger a mic break. If text provided, use it; otherwise auto-generate from context. |
| `radio_search` | `query`, `source` | Search stations/tracks. Returns results for the agent to present. |
| `radio_save` | `name` | Save current stream as a named preset |

### Toolset

Register as toolset `"radio"` in `toolsets.py`, gated on `shutil.which("mpv")`. Not included in `_HERMES_CORE_TOOLS` by default -- users opt in via config:

```yaml
toolsets:
  - core
  - radio
```

### Skill

A skill at `skills/media/hermes-radio/` providing the `/radio` slash command with subcommands (`/radio play`, `/radio crate`, `/radio soma`, etc.). The skill wraps the tool calls with conversational context.

### Session memory

Listening history persisted in the Hermes session DB. Each track played logs: timestamp, source, track metadata, duration listened. This feeds the LLM context for mic break generation and enables "what was that song?" recall. If Honcho is configured, listening sessions also sync to the user model.

### CLI subcommand

New entry point in `hermes_cli/commands.py`:

```bash
hermes radio                   # Launch interactive TUI
hermes radio play "query"      # Quick play from search
hermes radio crate             # Start crate digging (Radiooooo)
hermes radio soma              # Browse SomaFM channels
hermes radio presets           # List saved presets
```

---

## Configuration

```yaml
# ~/.hermes/config.yaml

radio:
  default_source: "crate"           # crate | stream | local
  default_volume: 80

  mic_breaks:
    enabled: true
    frequency: "every_track"       # every_track | every_n (+ interval) | manual
    interval: 3                     # if frequency is every_n, break every N tracks
    persona: "encyclopedic"       # deadpan | enthusiastic | conspiratorial | encyclopedic
    pre_generate: true             # render next mic break while current track plays
    duck_volume: 30               # primary volume during mic break (0-100)
    duck_ramp_ms: 500             # fade duration for volume ducking

  crate:
    decades: [1950, 1960, 1970, 1980, 1990]
    moods: ["slow", "weird"]
    countries: []                  # empty = random country discovery
    weighted_decades: true         # use Acephale's bell-curve weighting

  visualizer:
    enabled: true
    style: "bars"                 # bars | wave | none

  presets:
    defcon:
      source: "somafm"
      channel: "defcon"
    tokyo-night:
      source: "radio_garden"
      channel_id: "abc123"
    nts-1:
      source: "custom"
      url: "https://stream-relay-geo.ntslive.net/stream"
    senegal-70s:
      source: "crate"
      decades: [1970]
      countries: ["SEN"]
      moods: ["slow", "fast"]
```

---

## Implementation Plan

### Phase 1: Core playback

- [ ] Python mpv IPC client (spawn, connect, command, event loop)
- [ ] Radiooooo API client (Python port of Acephale's TypeScript client)
- [ ] Crate dig loop: fetch track -> play -> pre-fetch next -> gapless transition
- [ ] Basic CLI playback: `hermes radio crate` plays Radiooooo tracks in terminal
- [ ] Hermes tool registration (`radio_play`, `radio_stop`, `radio_skip`, `radio_status`)

### Phase 2: Live radio + sources

- [ ] Radio Browser API client (search, resolve stream URL)
- [ ] SomaFM client (channel list, stream URLs)
- [ ] Radio Garden client (place search, channel resolve, stream redirect)
- [ ] ICY metadata extraction from mpv events
- [ ] Stream auto-reconnect with exponential backoff
- [ ] Custom station presets in config
- [ ] `radio_tune`, `radio_search`, `radio_save` tools

### Phase 3: Mic breaks

- [ ] Second mpv instance for voice playback
- [ ] Volume ducking with smooth ramp via IPC
- [ ] LLM commentary prompt builder (track context, history, persona)
- [ ] Pre-generation pipeline (render next break while current track plays)
- [ ] Mic break triggers (track transition, timer, manual)
- [ ] `radio_mic_break` tool
- [ ] Audio cache management (`~/.hermes/audio_cache/radio/`)

### Phase 4: TUI

- [ ] Alt-screen rich/textual layout with now-playing, progress, dial
- [ ] Keyboard input handler (non-blocking via prompt_toolkit or curses)
- [ ] Channel dial strip with preset navigation
- [ ] Spectrum visualizer (optional, bars mode)
- [ ] Track info overlay
- [ ] Search overlay

### Phase 5: Polish

- [ ] Listening history in session DB
- [ ] Honcho sync for cross-session music preferences
- [ ] `/radio` skill with subcommands
- [ ] Local file playback mode
- [ ] Hermes CLI status line integration (show now-playing when radio is active)
- [ ] Graceful shutdown with sign-off mic break

---

## Open Decisions

| Decision | Options | Recommendation |
|---|---|---|
| TUI framework | `rich` (already dep) vs `textual` (richer widgets, new dep) vs raw `curses` | `textual` -- built on rich, proper widget system, reactive, handles input natively. Worth the new dependency for a full-screen TUI. |
| Spectrum visualizer | mpv `af=lavfi=showfreqs` + parse vs. mpv `ao=pcm` + FFT in Python vs. skip it | Use mpv's `af=lavfi=astats=metadata=1` to get RMS/peak levels per frame via metadata events. Simpler than full FFT, good enough for a bar display. Full FFT is a stretch goal. |
| LLM for commentary | User's configured Hermes model vs. dedicated lightweight model vs. hardcoded templates | Use user's configured model via the existing `auxiliary_client` (already supports vision/summarization side tasks). Falls back to templates if no LLM configured or if rate-limited. |
| Radiooooo rate limiting | Unknown -- no official docs. Acephale runs at ~2 tracks/minute without issues. | Conservative default: 1 track fetch per 10 seconds max. Retry with backoff on 429s. Pre-fetch only 1 track ahead. |
| Radio Garden reliability | Unofficial API, could change or block. No versioning. | Treat as best-effort. Cache the places list locally (refresh daily). Degrade gracefully to Radio Browser if Radio Garden is down. |
| Mic break voice consistency | Same voice always vs. voice per persona vs. random | Single voice per persona, configured in `radio.mic_breaks.persona`. Map each persona to a recommended TTS voice but let the user override via `tts.edge.voice` / `tts.elevenlabs.voice_id`. |

> **System dependency** -- mpv is the only required system dependency beyond Python. Install: `brew install mpv` (macOS), `apt install mpv` (Debian/Ubuntu), `choco install mpv` (Windows). The tool's `check_fn` gates on `shutil.which("mpv")`.
