"""Entry point.

  python run.py              # interactive text mode (works everywhere)
  python run.py --voice      # full voice loop (mic + Whisper + TTS)
  python run.py --api        # also start the local FastAPI/WebSocket server
  python run.py --say "..."  # process one command and exit
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Windows AI Voice Assistant")
    parser.add_argument("--voice", action="store_true", help="Run the full voice pipeline")
    parser.add_argument("--api", action="store_true", help="Start the local FastAPI server too")
    parser.add_argument("--wake", action="store_true", help="Require the wake word before each command")
    parser.add_argument("--say", type=str, default="", help="Process a single text command and exit")
    args = parser.parse_args()

    from app.config.settings import settings
    from app.core.assistant import Assistant
    from app.core.orchestrator import Orchestrator
    from app.core.memory import Memory
    from app.storage.database import Database

    mode = "PRODUCTION" if settings.is_production else "DEVELOPMENT (destructive actions simulated)"
    brain = settings.openai_model if settings.llm_enabled else "rule-based (no API key set)"

    db = Database()
    memory = Memory(db)
    orch = Orchestrator(memory=memory)

    if args.api:
        from app.api.server import start_api

        start_api(orch)
        print(f"API server: http://{settings.agent_host}:{settings.agent_port}")

    if args.say:
        result = orch.handle(args.say)
        print(result.response)
        return 0

    print("=" * 50)
    print("AI Assistant started.")
    print(f"Mode:   {mode}")
    print(f"Brain:  {brain}")
    if args.voice:
        print('Say "Hey Assistant" or just speak. Ctrl+C to quit.')
    else:
        print("Type a command, or 'quit' to exit. Use --voice for microphone mode.")
    print("=" * 50)

    if args.voice:
        assistant = Assistant(orch, require_wake_word=args.wake)
        try:
            assistant.run()
        except Exception as exc:
            print(f"Voice pipeline failed to start: {exc}")
            print("Check microphone access and that faster-whisper/whisper are installed.")
            return 1
        return 0

    # interactive text mode
    from app.voice.text_to_speech import PrintTTS

    tts = PrintTTS()
    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return 0
        if user.lower() in ("quit", "exit", "bye"):
            tts.speak("Goodbye!")
            return 0
        if not user:
            continue
        result = orch.handle(user)
        tts.speak(result.response)


if __name__ == "__main__":
    sys.exit(main())
