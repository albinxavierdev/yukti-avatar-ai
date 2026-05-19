"""Quick check that Groq API + local setup work."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from yukti.config import ENV_FILE
from yukti.llm import chat

load_dotenv(ENV_FILE)


def main():
    reply, _ = chat("Say hello in one short sentence.")
    print("Groq:", reply)


if __name__ == "__main__":
    main()
