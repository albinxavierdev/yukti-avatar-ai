"""Thread pools for blocking LLM and TTS work."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

_cpu_workers = max(1, (os.cpu_count() or 2) - 1)
llm_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yukti-llm")
tts_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yukti-tts")
