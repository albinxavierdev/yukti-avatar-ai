#!/usr/bin/env python3
"""Compare batch /api/chat vs streaming /api/chat/stream latency."""

from __future__ import annotations

import json
import statistics
import sys
import time

import httpx

BASE = "http://127.0.0.1:8765"
MESSAGE = "Hello! Tell me one fun fact about the moon, in two short sentences."
RUNS = 3


def post_json(path: str, payload: dict) -> dict:
    with httpx.Client(timeout=120) as client:
        r = client.post(f"{BASE}{path}", json=payload)
        r.raise_for_status()
        return r.json()


def bench_batch() -> dict[str, float]:
    t0 = time.perf_counter()
    data = post_json("/api/chat", {"message": MESSAGE, "voice": "F2", "lang": "en"})
    total_ms = (time.perf_counter() - t0) * 1000
    audio_len = len(data.get("audio_base64") or "")
    return {
        "total_ms": total_ms,
        "ttf_audio_ms": total_ms,
        "audio_chunks": 1,
        "reply_chars": len(data.get("reply") or ""),
        "audio_b64_chars": audio_len,
    }


def _parse_sse_chunk(buf: str) -> tuple[list[dict], str]:
    events: list[dict] = []
    while "\n\n" in buf:
        block, buf = buf.split("\n\n", 1)
        for line in block.split("\n"):
            if not line.startswith("data:"):
                continue
            raw = line[5:].lstrip()
            if raw:
                events.append(json.loads(raw))
    return events, buf


def bench_stream() -> dict[str, float]:
    t0 = time.perf_counter()
    ttf_text: float | None = None
    ttf_audio: float | None = None
    audio_chunks = 0
    reply = ""
    metrics: dict | None = None
    buf = ""

    with httpx.Client(timeout=120) as client:
        with client.stream(
            "POST",
            f"{BASE}/api/chat/stream",
            json={"message": MESSAGE, "voice": "F2", "lang": "en"},
        ) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                buf += chunk.decode(errors="replace")
                events, buf = _parse_sse_chunk(buf)
                for ev in events:
                    now = time.perf_counter()
                    if ev.get("type") == "text_delta" and ttf_text is None:
                        ttf_text = (now - t0) * 1000
                    if ev.get("type") == "audio":
                        audio_chunks += 1
                        if ttf_audio is None:
                            ttf_audio = (now - t0) * 1000
                    if ev.get("type") == "done":
                        reply = ev.get("reply") or reply
                        metrics = ev.get("metrics")

    total_ms = (time.perf_counter() - t0) * 1000
    out = {
        "total_ms": total_ms,
        "ttf_text_ms": ttf_text,
        "ttf_audio_ms": ttf_audio or total_ms,
        "audio_chunks": audio_chunks,
        "reply_chars": len(reply),
    }
    if metrics:
        out["server_metrics"] = metrics
    return out


def avg_runs(fn) -> dict[str, float]:
    rows = [fn() for _ in range(RUNS)]
    keys = rows[0].keys()
    out: dict[str, float] = {}
    for k in keys:
        if k == "server_metrics":
            continue
        vals = [r[k] for r in rows if r.get(k) is not None]
        if vals and all(isinstance(v, (int, float)) for v in vals):
            out[k] = round(statistics.mean(vals), 1)
    return out


def main() -> int:
    print(f"Benchmark: {RUNS} runs, message={MESSAGE!r}\n")
    try:
        httpx.get(f"{BASE}/", timeout=5).raise_for_status()
    except httpx.HTTPError as e:
        print(f"Server not reachable at {BASE}: {e}", file=sys.stderr)
        return 1

    batch = avg_runs(bench_batch)
    stream = avg_runs(bench_stream)

    ttf_improve = batch["ttf_audio_ms"] - stream["ttf_audio_ms"]
    ttf_pct = (ttf_improve / batch["ttf_audio_ms"] * 100) if batch["ttf_audio_ms"] else 0
    total_delta = stream["total_ms"] - batch["total_ms"]

    print("=== Batch POST /api/chat (legacy path) ===")
    for k, v in batch.items():
        print(f"  {k}: {v}")
    print()
    print("=== Stream POST /api/chat/stream (new path) ===")
    for k, v in stream.items():
        print(f"  {k}: {v}")
    print()
    print("=== Comparison ===")
    print(f"  Time to first audio: {batch['ttf_audio_ms']:.1f} ms → {stream['ttf_audio_ms']:.1f} ms")
    print(f"    improvement: {ttf_improve:.1f} ms faster ({ttf_pct:.1f}% reduction)")
    print(f"  Total end-to-end:    {batch['total_ms']:.1f} ms → {stream['total_ms']:.1f} ms")
    print(f"    delta: {total_delta:+.1f} ms")
    print(f"  Audio chunks:        1 → {stream['audio_chunks']:.0f}")

    report = {
        "batch": batch,
        "stream": stream,
        "comparison": {
            "ttf_audio_improvement_ms": round(ttf_improve, 1),
            "ttf_audio_improvement_pct": round(ttf_pct, 1),
            "total_delta_ms": round(total_delta, 1),
        },
    }
    out_path = "benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
