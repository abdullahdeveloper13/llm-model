# Windows AI Voice Assistant

A production-quality, **local** voice-controlled assistant for Windows.
You speak ("Open WhatsApp", "Shutdown my computer"), it transcribes your
speech, understands the intent with an LLM (or an offline rule-based fallback),
and executes **registered, permission-checked tools** on your actual machine.

No browser is required. No arbitrary shell commands are ever executed.
(An optional Next.js control panel scaffold also lives in this repo; the
assistant never depends on it.)

## 1. Project Overview

- **Voice pipeline**: microphone → silence-trimmed recording → local
  faster-whisper STT → LLM intent parsing → tool execution → pyttsx3 TTS.
- **AI brain**: OpenAI-compatible tool-calling. The model may only *request*
  tools from a fixed registry; it can never run generated code.
- **Safety layer**: SAFE / CONFIRMATION_REQUIRED / BLOCKED tool categories,
  with pending-action confirmations that expire after a timeout.
- **Development mode**: destructive tools (`shutdown`, `restart`) are
  simulated (`[SIMULATION] ...`) until you set `ASSISTANT_MODE=production`.
- **Optional API**: FastAPI + WebSocket so a UI can be added without touching
  the core.

## 2. Architecture

```
User Voice → Microphone → Speech-to-Text (faster-whisper)
           → AI Brain (LLM / rule fallback) → Plan (tool + validated args)
           → Permission Layer (safe | confirm | blocked)
           → Tool Executor → Windows apps / browser / system / WhatsApp
           → Result → Text-to-Speech (pyttsx3) → User
```

Modules: `app/core` (brain, orchestrator, memory, assistant), `app/agent`
(planner, executor, permissions, registry), `app/tools` (all capabilities),
`app/voice` (mic/STT/TTS/wake word), `app/api` (FastAPI/WebSocket),
`app/storage` (SQLite), `app/config`, `app/utils`.

## 3. Requirements

- Windows 10/11, Python 3.11+
- A microphone (voice mode only)
- Optional: an OpenAI-compatible API key. Without one, the assistant runs in
  rule-based mode and still understands the standard command set.

## 4. Installation

```powershell
cd c:\llm-model
python -m pip install -r requirements.txt
Copy-Item .env.example .env   # then edit .env
```

## 5. Environment Variables (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | *(empty)* | Leave empty for offline rule-based mode |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model used for intent parsing |
| `AGENT_HOST` / `AGENT_PORT` | `127.0.0.1` / `8000` | Local API bind address |
| `ASSISTANT_MODE` | `development` | `development` simulates destructive tools; `production` executes them |
| `CONFIRMATION_TIMEOUT` | `60` | Seconds before a pending confirmation expires |
| `APP_SHORTCUTS_PATH` | `data/app_shortcuts.json` | Optional app-name → path overrides |
| `WHISPER_MODEL` | `base` | faster-whisper model size |
| `WHISPER_BEAM_SIZE` / `WHISPER_MIN_SILENCE_MS` | `5` / `500` | multilingual decoding and VAD tuning |
| `WHISPER_NO_SPEECH_THRESHOLD` | `0.6` | faster-whisper silence rejection |
| `TTS_RATE` | `180` | Speech rate (words/min) |
| `WAKE_WORD` | `hey assistant` | Wake phrase |
| `SAMPLE_RATE` / `FRAME_MS` | `16000` / `30` | microphone PCM and VAD frame settings |
| `PRE_ROLL_MS` / `SILENCE_LIMIT_MS` | `300` / `750` | first-word protection and trailing silence |
| `MAX_RECORD_MS` / `MIN_SPEECH_MS` | `15000` / `240` | utterance bounds |
| `VAD_THRESHOLD` / `VAD_NOISE_MULTIPLIER` | `0.010` / `3.0` | adaptive microphone threshold |
| `MICROPHONE_DEVICE` | *(default device)* | optional sounddevice input device |

Never commit `.env`.

## 6. How to Run

```powershell
python run.py              # interactive text mode (works everywhere)
python run.py --voice      # full voice loop (mic + Whisper + TTS)
python run.py --voice --wake  # require "hey assistant" before each command
python run.py --api        # start the local FastAPI/WebSocket server too
python run.py --say "open notepad"   # one-shot command
python run.py --install-startup       # install per-user Windows Startup entry
python run.py --remove-startup        # remove that entry
```

API endpoints: `GET /health`, `POST /assistant/command` `{"text": ...}`,
`POST /assistant/confirm` `{"answer": "yes"|"no"}`, `GET /commands`, WS `/ws`.

## 7. How Voice Recognition Works

`app/voice/microphone.py` records 16 kHz mono float32 audio, calibrates a short
noise floor, keeps pre-roll, and stops after configured trailing silence or a
maximum utterance duration. `WhisperSTT` runs faster-whisper locally with
automatic language detection and no previous-text carryover. TTS is pyttsx3
(Windows SAPI5, offline); capture is stopped before TTS and resumed afterward.

## 8. How the AI Brain Works

`Planner` sends your text (plus recent history) to the LLM with the tool
schemas. The model replies with either a tool call (validated against the
registry + a Pydantic-built schema; unknown tools are rejected) or a
conversation reply. If the LLM is unavailable, `RuleBasedBrain` parses the
standard command set locally.

## 9. Tool Architecture

All tools subclass `app/tools/base.Tool` (name, description, JSON schema,
category, `execute()`). `ToolRegistry` is the single source of truth; the
executor is the only code that calls `execute()`. Current tools:

`open_app`, `close_app`, `window_control`, `open_website`, `google_search`,
`browser_navigation`, `open_whatsapp`, `whatsapp_open_chat`,
`whatsapp_message_auto`, `whatsapp_call_auto`, legacy `whatsapp_call`,
`shutdown`, `restart`, `cancel_shutdown`, `system_info`, `search_files`,
`file_operation`, `delete_file`, `media_control`, `type_text`, and
`press_keys`.

## 10. Permission System

- **SAFE** (run immediately): open app/website, web search, system info,
  media, cancel shutdown.
- **CONFIRMATION_REQUIRED**: shutdown, restart, delete file, and the legacy
  contact-book WhatsApp call flow. Automatic WhatsApp message/call tools are safe.
  The assistant asks "Are you sure…?", stores a `PendingAction` that expires
  after `CONFIRMATION_TIMEOUT`, and only proceeds on a clear yes/no.
- **BLOCKED**: `run_shell`, `run_powershell`, credential access, security
  bypasses — rejected regardless of what the LLM says. External binaries are
  limited to an allow-list in `app/utils/security.py`.

## 11. WhatsApp Automation (honest scope)

- **"Open WhatsApp"**: launches WhatsApp Desktop if installed. ✔
- **Legacy "Call Ahmed" flow**: WhatsApp has **no official public API** for third-party
  call initiation, and WhatsApp Desktop exposes no supported automation
  interface. This project therefore resolves the contact in your local
  contact book (`data/contacts.json`) and opens the official
  `https://wa.me/<E164>` deep link — you press the call button yourself.
  No screen-coordinate automation, no reverse-engineered APIs. Ambiguous
  names (e.g. two "Ahmed"s) are **never guessed**: the assistant lists the
  matches and asks which one you mean.
- `WhatsAppProvider` is an abstraction so a future official provider can be
  swapped in without touching the rest of the code.

Setup contacts:

```json
// data/contacts.json
{ "Ahmed Raza": { "phone": "+923001234567", "aliases": ["ahmed"] } }
```

Automatic `whatsapp_message_auto` and `whatsapp_call_auto` use WhatsApp
Desktop's UI Automation tree and do not require `data/contacts.json`. They
search for a chat, locate accessible controls, and return failure if a required
control or post-action verification is unavailable. The legacy
`whatsapp_call` contact-book/deep-link tool remains only for compatibility.

## 12. How to Add New Tools

1. Create a class in `app/tools/<group>/...` subclassing `Tool` with
   `name`, `description`, `schema`, `category`, and `execute(**kwargs)`.
2. Add it to `build_default_registry()` in `app/agent/registry.py`.
3. Add tests. Nothing else changes — the LLM sees the new tool automatically.

## 13. Testing

```powershell
python -m pytest tests -q
```

Dangerous tools are tested with mocks only; `shutdown`/`restart` are
simulated in development mode.

## 14. Security Considerations

- The LLM can only *request* registered tools; `Executor` is the sole
  execution path and validates everything.
- All tool arguments are validated through Pydantic schemas.
- External binaries are limited to a code-reviewed allow-list.
- Deletion uses Recycle Bin and only inside user folders.
- Logs redact API keys/tokens; nothing sensitive is stored in SQLite.

## 15. Troubleshooting

- **Microphone errors**: check Windows privacy settings → Microphone access.
- **"I didn't catch that"**: noise or level too low; try `WHISPER_MODEL=small`.
- **App not found**: add an entry to `data/app_shortcuts.json`,
  e.g. `{"whatsapp": "C:\\...\\WhatsApp.lnk"}`.
- **No TTS voice**: install a Windows speech voice, or adjust `TTS_RATE`.
- **API won't start**: port already in use — change `AGENT_PORT`.

## Example Voice Commands

- "Open WhatsApp" / "Can you start Chrome?" / "Launch VS Code"
- "Open YouTube" / "Search Google for Next.js tutorials"
- "What is my CPU usage?" / "What is my RAM usage?"
- "Shutdown my computer" → "yes"/"no" · "Cancel shutdown"
- "Call Ahmed" (requires `data/contacts.json`; ambiguous names ask back)
- "Play music" / "Volume up" · "Hello" / "What can you do?"

## Known Limitations

- Whisper downloads a model (~150 MB for `base`) on first voice run.
- WhatsApp calling cannot be fully automated — see §11 (a WhatsApp platform
  restriction, not a project shortcut).
- Wake word matching is transcript-based; install porcupine/openWakeWord and
  extend `app/voice/wake_word.py` for always-on detection.
