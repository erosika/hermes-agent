# CLI Radio Player: Technical Research

> Technical research for a CLI pirate radio player with TTS mic breaks and internet radio station aggregation.

**Stack:** TypeScript / Node.js
**Date:** 2026-03-14

---

## Contents

1. [Radio Station Directories](#1-radio-station-directories)
2. [SomaFM API](#2-somafm-api)
3. [Radio Browser API](#3-radio-browser-api)
4. [Icecast Directory](#4-icecast-directory-dirxiphorg)
5. [TTS for Mic Breaks](#5-tts-for-mic-breaks)
6. [CLI Audio Playback](#6-cli-audio-playback)
7. [Recommended Architecture](#7-recommended-architecture)
8. [Final Recommendations](#8-final-recommendations)

---

## 1. Radio Station Directories

Three primary open directories provide API access to internet radio streams. Between them you get coverage of curated indie stations, the entire long tail of community radio, and the Icecast/Shoutcast ecosystem.

| Directory     | Stations    | Auth | Format                | Character                              |
|---------------|-------------|------|-----------------------|----------------------------------------|
| SomaFM        | ~40 curated | None | JSON                  | High-quality curated indie/underground |
| Radio Browser | 45,000+     | None | JSON/XML/CSV/M3U/PLS  | Community-maintained global directory  |
| Icecast       | ~350+       | None | XML (yp.xml)          | Icecast-native stations, many underground |

---

## 2. SomaFM API

SomaFM is a listener-supported, commercial-free internet radio service based in San Francisco. It runs ~40 curated channels spanning ambient, electronic, indie, lounge, metal, and experimental genres. The aesthetic is perfect for a pirate radio vibe.

### Channels Endpoint

```
GET https://api.somafm.com/channels.json
```

No authentication, no rate limiting documented.

### Channel Object Structure

```json
{
  "id": "groovesalad",
  "title": "Groove Salad",
  "description": "A nicely chilled plate of ambient/downtempo...",
  "genre": "ambient|electronic",         // pipe-separated
  "dj": "Rusty",
  "djmail": "rusty@somafm.com",
  "lastPlaying": "Artist - Track",       // current/recent track
  "listeners": "1234",                   // string, not number
  "image": "https://...",                // 120px thumbnail
  "largeimage": "https://...",           // 256px
  "xlimage": "https://...",              // 512px
  "playlists": [
    { "url": "https://somafm.com/groovesalad130.pls", "format": "aac", "quality": "highest" },
    { "url": "https://somafm.com/groovesalad.pls",    "format": "mp3", "quality": "high" },
    { "url": "https://somafm.com/groovesalad32.pls",  "format": "aacp", "quality": "low" }
  ]
}
```

### Stream URL Patterns

| Pattern                           | Format       | Example                    |
|-----------------------------------|--------------|----------------------------|
| `/{channel}{bitrate}.pls`         | PLS playlist | `/groovesalad130.pls`      |
| `/m3u/{channel}{bitrate}.m3u`     | M3U playlist | `/m3u/groovesalad130.m3u`  |
| `/nossl/{channel}{bitrate}.pls`   | PLS (HTTP)   | `/nossl/groovesalad130.pls`|

### Notable Channels for Pirate Radio Vibe

- `defcon` -- Music for hacking. Dark, edgy electronic
- `darkzone` -- Dark ambient, industrial
- `doomed` -- Dark industrial/ambient
- `sf1033` -- Ambient with SF police scanner overlay
- `vaporwaves` -- Vaporwave aesthetics
- `cliqhop` -- Intelligent dance music
- `fluid` -- Instrumental hip-hop
- `dubstep` -- Dubstep/deep bass
- `thetrip` -- Progressive house/trance
- `digitalis` -- Experimental electronic rock

> **Advantage:** SomaFM streams are high quality, reliable, and legal. The PLS files resolve to direct Icecast stream URLs that mpv can play natively. Song history available at `/{channel}/songhistory.html`.

---

## 3. Radio Browser API

The largest open directory of internet radio stations. Community-maintained, free, no auth required. Over 45,000 stations indexed with full metadata. This is the backbone for station discovery.

### Server Discovery

The API runs on multiple mirrors. Resolve `all.api.radio-browser.info` via DNS to get a list of available servers, then pick one at random for load balancing.

```ts
// Discover servers via DNS
const { resolve } = require('dns/promises');
const servers = await resolve('all.api.radio-browser.info');
// Use: https://{server}/json/stations/search
```

### Key Endpoints

#### Search Stations

```
GET/POST /{format}/stations/search

Parameters (all optional):
  name          -- station name (fuzzy)
  nameExact     -- exact match
  tag           -- single genre tag
  tagList       -- comma-separated tags (AND)
  country       -- full country name
  countrycode   -- ISO 3166-1 alpha-2
  language      -- language name
  codec         -- audio codec (mp3, aac, ogg...)
  bitrateMin    -- minimum kbps
  bitrateMax    -- maximum kbps
  is_https      -- HTTPS-only streams
  order         -- name|votes|clickcount|bitrate|random
  limit         -- results per page
  offset        -- pagination
  hidebroken    -- exclude offline stations
```

#### Curated Lists

```
GET /json/stations/topclick/{limit}      -- most popular
GET /json/stations/topvote/{limit}       -- highest rated
GET /json/stations/lastclick/{limit}     -- recently played
GET /json/stations/lastchange/{limit}    -- recently added
GET /json/stations/search?order=random   -- random discovery
```

#### Browse Metadata

```
GET /json/tags          -- all genre tags with counts
GET /json/countries     -- all countries with counts
GET /json/languages     -- all languages with counts
GET /json/codecs        -- all codecs with counts
```

#### Get Resolved Stream URL

```
GET /json/url/{stationuuid}

Returns:
{
  "url": "https://original.url/stream",
  "url_resolved": "https://actual.server/stream.mp3",  // direct stream
  "stationuuid": "abc-123-def"
}
// Also increments the station's click counter
```

### Station Object

```json
{
  "stationuuid": "abc-123",
  "name": "Underground FM",
  "url": "https://stream.example.com/radio",
  "url_resolved": "https://...",
  "homepage": "https://...",
  "favicon": "https://...",
  "tags": "electronic,underground,pirate",
  "country": "United States",
  "countrycode": "US",
  "language": "english",
  "codec": "MP3",
  "bitrate": 128,
  "votes": 42,
  "clickcount": 1337,
  "lastcheckok": 1,
  "hls": 0,
  "geo_lat": 37.7749,
  "geo_long": -122.4194
}
```

> **Usage Notes:** Set a descriptive `User-Agent` header. Use `url_resolved` for direct playback (bypasses playlist file parsing). Click counting is limited to once per IP per station per day. All GET params can be sent as POST with JSON body.

### Useful Tag Searches for Pirate Radio

```
"pirate", "underground", "independent", "college", "community",
"freeform", "experimental", "lo-fi", "punk", "diy",
"noise", "avant-garde", "alternative", "anarchist"
```

---

## 4. Icecast Directory (dir.xiph.org)

The Xiph.org Icecast directory provides a machine-readable XML feed of Icecast-registered stations. Smaller than Radio Browser but contains stations that may not appear elsewhere, particularly hobbyist and underground broadcasters.

### Endpoint

```
GET https://dir.xiph.org/yp.xml
```

### Entry Structure

```xml
<entry>
  <server_name>Underground Radio</server_name>
  <server_type>audio/mpeg</server_type>
  <bitrate>128</bitrate>
  <samplerate>44100</samplerate>
  <channels>2</channels>
  <listen_url>https://stream.example.com/radio</listen_url>
  <current_song>Artist - Track</current_song>
  <genre>electronic experimental</genre>
</entry>
```

Audio formats include `audio/mpeg` (MP3), `audio/aac`, `audio/aacp`, `application/ogg`, and `audio/mp4`. Bitrates range from 16 kbps (talk/scanner) to 1024 kbps (high-fidelity music). The `listen_url` values are direct stream URLs -- no playlist resolution needed.

> **Limitation:** The Icecast directory is a flat XML file with no search/filter API. You must fetch the entire file and filter client-side. Best treated as a supplementary source parsed on startup and cached.

---

## 5. TTS for Mic Breaks

For creating radio DJ-style announcements between songs or during station changes. The key requirement is generating natural-sounding speech, saving it to a file (or buffer), and inserting it into the audio playback stream.

### Option Comparison

| Solution    | Quality    | Cost    | Latency | Offline | Verdict     |
|-------------|------------|---------|---------|---------|-------------|
| Edge TTS    | High (neural) | Free | ~1-2s   | No      | RECOMMENDED |
| ElevenLabs  | Excellent  | $5+/mo  | ~2-4s   | No      | PREMIUM     |
| Piper TTS   | Good       | Free    | ~0.5s   | Yes     | FALLBACK    |
| say.js      | Low-Med    | Free    | ~0.2s   | Yes     | BASIC       |

### Edge TTS (Recommended Default)

Uses Microsoft Edge's online neural TTS service. No API key needed, no account required, high-quality neural voices, 400+ voices across 100+ languages. Free with no documented rate limits (uses the same endpoint as Edge browser's Read Aloud feature).

#### Best Node.js Packages

| Package               | Version | Last Updated | License | Notes                                           |
|-----------------------|---------|-------------|---------|--------------------------------------------------|
| `@andresaya/edge-tts` | 1.8.0   | 2025-12     | GPL-3.0 | Most complete API, streaming, word boundaries, 36+ output formats |
| `@bestcodes/edge-tts` | 3.0.1   | 2025-12     | MIT     | Clean API, streaming, <50kb bundle, MIT license  |
| `node-edge-tts`       | 1.2.10  | 2026-02     | MIT     | Actively maintained, simple promise API, subtitle support |

#### Usage with @bestcodes/edge-tts

```ts
import { EdgeTTS } from '@bestcodes/edge-tts';

const tts = new EdgeTTS();

// Generate to buffer
const audio = await tts.generateSpeech({
  text: "You're locked in to Underground FM, broadcasting from the edge of nowhere.",
  voice: "en-US-GuyNeural",       // male, natural
  rate: "-5%",                     // slightly slower for DJ vibe
  pitch: "-2Hz",                   // slightly lower pitch
});

// Or generate to file
await tts.generateSpeechToFile({
  text: "Next up, we've got something special...",
  voice: "en-US-AndrewNeural",
  outputPath: "/tmp/mic-break.mp3",
});

// Stream chunks for real-time playback
for await (const chunk of tts.streamSpeech({ text, voice })) {
  // pipe to audio output
}
```

#### Usage with @andresaya/edge-tts

```ts
import { EdgeTTS } from '@andresaya/edge-tts';

const tts = new EdgeTTS();

// Synthesize with full control
await tts.synthesize(
  "You're tuned in to the frequency. Don't touch that dial.",
  'en-US-DavisNeural',
  { rate: '-10%', volume: '+20%', pitch: '-5Hz' }
);

// Export
await tts.toFile("mic-break");        // auto-detects extension
const buffer = tts.toBuffer();          // get Buffer directly
const duration = tts.getDuration();     // seconds

// 36+ output formats available:
// MP3 (16/24/48kHz), Opus, WebM, OGG, WAV/PCM, AMR-WB, G.722, TrueSilk
```

#### Good DJ Voices (Edge TTS)

- `en-US-GuyNeural` -- deep male, warm radio tone
- `en-US-DavisNeural` -- confident male
- `en-US-AndrewNeural` -- natural male
- `en-US-AriaNeural` -- clear female
- `en-US-JennyNeural` -- friendly female
- `en-GB-RyanNeural` -- British male, good for pirate radio persona
- `en-AU-WilliamNeural` -- Australian male

### ElevenLabs (Premium Option)

State-of-the-art voice synthesis. Most natural-sounding option by far. Has voice cloning for creating a unique DJ persona. Costs money but quality is unmatched.

```
POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}

Headers:
  xi-api-key: your-api-key
  Content-Type: application/json

Body:
{
  "text": "You're listening to the signal.",
  "model_id": "eleven_multilingual_v2",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.8,
    "style": 0.3,
    "speed": 0.9
  }
}

Output formats: mp3_44100_128 (default), pcm_44100, wav_44100, opus_48000_128
Response: binary audio stream (application/octet-stream)
```

> **Pricing:** Free tier gives ~10k characters/month. Starter is $5/month for 30k chars. For occasional mic breaks (short phrases every few minutes), the free tier might suffice. Voice cloning requires a paid plan.

### Piper TTS (Offline Fallback)

Fast local neural TTS system. C++ core with Python bindings. Runs entirely offline. MIT-licensed. Repository has been archived; development moved to [piper1-gpl](https://github.com/OHF-Voice/piper1-gpl).

- 10.7k GitHub stars, well-established
- Multiple voice models per language at different quality levels
- Outputs raw PCM or WAV
- Very fast -- suitable for real-time generation
- Use from Node.js: shell out to the `piper` binary, pipe text in, get WAV out

```ts
// Shell out to piper from Node.js
import { execFile } from 'child_process';

const piper = execFile('piper', [
  '--model', 'en_US-lessac-medium.onnx',
  '--output_file', '/tmp/mic-break.wav'
]);
piper.stdin.write("Coming up next on the underground frequency...");
piper.stdin.end();
```

### say.js (System TTS Fallback)

Uses platform-native TTS: macOS `say`, Windows SAPI, Linux Festival. Quality varies by platform -- macOS has decent neural voices, Linux Festival sounds robotic. Good as a zero-dependency fallback.

```ts
import say from 'say';

// Speak aloud
say.speak("You're listening to pirate radio.", 'Samantha', 0.9);

// Export to WAV (macOS/Windows only)
say.export("Station identification.", 'Alex', 0.85, '/tmp/id.wav', (err) => {
  // file ready
});
```

> **Limitation:** No export support on Linux. No streaming API. Limited voice quality on non-macOS platforms.

### Mic Break Audio Pipeline

The TTS output needs to be mixed into the radio stream. The cleanest approach is to generate TTS to a temp file, then have the playback engine duck the radio volume and play the mic break as an overlay or interstitial.

```
Mic break trigger (timer / track change / manual)
  --> Generate TTS (Edge TTS / Piper)
  --> Save to temp .mp3
  --> Duck radio volume (mpv volume command)
     OR Pause radio stream
  --> Play mic break (secondary mpv instance)
  --> Restore radio (volume / resume)
```

---

## 6. CLI Audio Playback

### Option Comparison

| Backend      | Stream Support | IPC Control       | Codec Support  | Install             | Verdict     |
|--------------|---------------|-------------------|----------------|---------------------|-------------|
| mpv          | Excellent     | JSON IPC socket   | Everything     | `brew install mpv`  | RECOMMENDED |
| ffplay       | Good          | None (stdin only) | Everything     | `brew install ffmpeg`| VIABLE     |
| sox/play     | Limited       | None              | WAV, MP3, FLAC | `brew install sox`  | LIMITED     |
| node-speaker | PCM only      | Native Node       | Raw PCM only   | `bun add speaker`   | LOW-LEVEL   |
| play-sound   | Files only    | Process kill      | Depends on backend | `bun add play-sound` | SIMPLE  |

### mpv (Recommended)

mpv is the clear winner for a CLI radio player. It handles every codec, every stream format (HTTP, HTTPS, HLS, Icecast, PLS, M3U), provides rich metadata extraction from streams, and exposes a full-featured JSON IPC protocol for programmatic control.

#### Audio-Only Mode

```bash
# Launch mpv for audio-only playback with IPC control
mpv --no-video --no-audio-display \
    --input-ipc-server=/tmp/mpv-radio.sock \
    "https://ice1.somafm.com/defcon-128-mp3"
```

#### JSON IPC Protocol

```jsonc
// Connect via Unix domain socket at /tmp/mpv-radio.sock
// All communication is newline-delimited JSON

// Send command:
{ "command": ["set_property", "volume", 50] }

// Get property:
{ "command": ["get_property", "media-title"] }

// Observe property changes:
{ "command": ["observe_property", 1, "metadata"] }

// Load new stream:
{ "command": ["loadfile", "https://stream.url", "replace"] }

// Pause/Resume:
{ "command": ["set_property", "pause", true] }
{ "command": ["set_property", "pause", false] }
```

#### node-mpv Wrapper

The `node-mpv` npm package (v1.5.0, by j-holub) wraps the IPC protocol in a clean promise-based Node.js API. Zero runtime dependencies -- it spawns mpv as a child process and communicates over the IPC socket.

```ts
import mpvAPI from 'node-mpv';

const mpv = new mpvAPI({
  audio_only: true,
  socket: '/tmp/mpv-radio.sock',
  time_update: 1,     // emit timeposition events every 1s
  verbose: false,
});

await mpv.start();

// Load a radio stream
await mpv.load('https://ice1.somafm.com/defcon-128-mp3');

// Playback control
await mpv.pause();
await mpv.resume();
await mpv.volume(75);
await mpv.adjustVolume(-10);
await mpv.mute();

// Metadata
const title = await mpv.getTitle();      // stream title / now playing
const meta = await mpv.getMetadata();    // full metadata object

// Queue management
await mpv.append('https://another-stream.url');
await mpv.next();
await mpv.prev();
await mpv.jump(2);  // zero-based index

// Events
mpv.on('started', () => console.log('Playback started'));
mpv.on('stopped', () => console.log('Playback stopped'));
mpv.on('status', (status) => { /* volume, pause state, etc. */ });
mpv.on('timeposition', (pos) => { /* current position */ });

// Direct property access (any mpv property)
const codec = await mpv.getProperty('audio-codec-name');
const bitrate = await mpv.getProperty('audio-bitrate');

// Cleanup
await mpv.quit();
```

#### Dual-Instance Pattern for Mic Breaks

Run two mpv instances: one for the radio stream, one for TTS/mic break playback. This allows ducking the radio volume while overlaying the announcement without interrupting the stream connection.

```ts
const radio = new mpvAPI({ audio_only: true, socket: '/tmp/mpv-radio.sock' });
const voice = new mpvAPI({ audio_only: true, socket: '/tmp/mpv-voice.sock' });

async function micBreak(text: string) {
  // 1. Generate TTS
  const tts = new EdgeTTS();
  await tts.generateSpeechToFile({
    text, voice: 'en-US-GuyNeural',
    outputPath: '/tmp/mic-break.mp3'
  });

  // 2. Duck radio volume
  await radio.volume(20);

  // 3. Play announcement
  await voice.load('/tmp/mic-break.mp3');

  // 4. Wait for announcement to finish
  await new Promise(r => voice.once('stopped', r));

  // 5. Restore radio volume
  await radio.volume(100);
}
```

### node-speaker (Low-Level Alternative)

A Node.js Writable stream backed by mpg123 output modules. Accepts raw interleaved PCM data and sends it to the system audio output. Useful if you want to build a fully in-process audio pipeline, but requires decoding audio to PCM yourself.

```ts
import Speaker from 'speaker';

const speaker = new Speaker({
  channels: 2,
  bitDepth: 16,
  sampleRate: 44100,
  signed: true,
});

// Pipe decoded PCM audio to speakers
decodedStream.pipe(speaker);

// Events: "open", "flush", "close"
// Supported backends: ALSA (Linux), CoreAudio (macOS), winmm (Windows)
```

> **Why not node-speaker for radio:** It only accepts raw PCM, meaning you'd need to separately decode MP3/AAC/Ogg streams. It also requires native compilation (node-gyp), and mixing multiple audio sources (radio + TTS) would require manual PCM buffer interleaving. mpv handles all of this transparently.

### play-sound (Simple File Playback)

Thin wrapper that spawns a system audio player to play a file. Auto-detects available players: `mplayer`, `afplay` (macOS), `mpg123`, `play` (sox), `cvlc`, etc. Useful for one-shot sound effects but not for streaming radio.

---

## 7. Recommended Architecture

```
CLI Interface (Ink / blessed / raw ANSI)
  --> Radio Engine
        --> Station Manager
              --> SomaFM API
              --> Radio Browser API
              --> Icecast Directory
              --> Local Favorites (JSON file)
        --> Playback Controller
              --> mpv instance #1 (radio stream)
              --> mpv instance #2 (voice / effects)
        --> DJ Module (mic breaks)
              --> TTS Engine (Edge TTS primary, Piper fallback)
              --> Announcement Templates
              --> Break Scheduler (timer / track change)
```

### Key Architectural Decisions

- **mpv as playback backend:** External process controlled via JSON IPC. Handles all codec/protocol complexity. Two instances enable radio + voice overlay without interruption
- **Station aggregation at startup:** Fetch SomaFM channels.json and cache. Lazy-load Radio Browser searches. Parse Icecast yp.xml once and cache. Merge into unified station model
- **TTS with graceful degradation:** Try Edge TTS first (best quality, free). Fall back to Piper if offline. Last resort: system TTS via say.js
- **Mic break scheduling:** Timer-based (every N minutes), event-driven (on track change detected via mpv metadata events), or manual trigger. Pre-generate next announcement during playback for zero-latency transitions
- **Announcement templates:** Parameterized strings with station name, current track, time, listener count. Vary phrases to avoid repetition. Possible LLM integration for dynamic DJ patter

### Dependency Stack

```jsonc
// Core
"node-mpv": "^1.5.0"          // mpv IPC wrapper (zero deps)

// TTS (pick one or layer them)
"@bestcodes/edge-tts": "^3.0"  // MIT, clean API, <50kb
// OR
"@andresaya/edge-tts": "^1.8"  // GPL-3, more features/formats

// System requirement
// mpv must be installed: brew install mpv
```

---

## 8. Final Recommendations

- [x] **Radio streams:** Radio Browser API as primary discovery engine (45k+ stations, excellent search). SomaFM as curated preset collection. Icecast directory as supplementary source
- [x] **Audio playback:** mpv via node-mpv wrapper. Two instances (radio + voice). JSON IPC gives full programmatic control including volume, metadata, pause, stream switching
- [x] **TTS engine:** Edge TTS as default (free, neural quality, 400+ voices, no API key). Support ElevenLabs as premium upgrade path. Piper as offline fallback
- [x] **Mic break flow:** Generate TTS to temp file, duck radio volume via mpv IPC, play announcement on secondary mpv instance, restore volume on completion
- [x] **Pre-generation:** Generate next mic break during playback to eliminate latency. Cache generated audio for repeated announcements (station IDs, time checks)

### Key Trade-offs

**mpv (external process)** vs **node-speaker (in-process)**

| mpv                              | node-speaker                    |
|----------------------------------|---------------------------------|
| Pro: handles all codecs/protocols | Pro: no external dependency    |
| Pro: rich IPC for full control   | Pro: fine-grained PCM mixing   |
| Pro: battle-tested reliability   | Con: must decode all formats   |
| Con: requires system install     | Con: native compilation        |
| Con: two processes for overlay   | Con: manual buffer management  |

**Edge TTS (online)** vs **ElevenLabs (premium)**

| Edge TTS                         | ElevenLabs                      |
|----------------------------------|---------------------------------|
| Pro: free, no API key            | Pro: best voice quality         |
| Pro: neural quality voices       | Pro: voice cloning              |
| Pro: 400+ voices, 100+ languages| Pro: official stable API        |
| Con: requires internet           | Con: costs money                |
| Con: unofficial API, could break | Con: rate limits                |

> **Minimum viable stack:** `node-mpv` + `@bestcodes/edge-tts` + Radio Browser API. Two npm packages, one system dependency (mpv), zero API keys. This gets you streaming radio with DJ mic breaks in a minimal, maintainable setup.
