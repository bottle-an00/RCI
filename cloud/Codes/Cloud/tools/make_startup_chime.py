"""시동 차임 static/audio/startup.wav 생성기 — MP3 강제구동(DID 0x0209)용.

왜 합성하는가
    차량 제조사의 실제 시동음은 저작물이고 음향 상표(사운드마크)일 수 있어, 영상
    사이트 등에서 추출해 쓰면 저작권 침해다. 그래서 **직접 합성한 오리지널**을 쓴다.
    이 파일이 리포에 함께 있는 이유가 그것이다 — startup.wav 가 어디서 왔는지(누구
    것을 가져온 게 아니라 이 스크립트가 만든 것인지)를 코드로 증명한다.

    정식 음원을 사내 브랜드 자산 채널이나 라이선스로 확보하면 startup.wav 만
    교체하면 된다. 배선(_model3d.html 의 <audio> + rci-live.js 의 SOUNDS)은 그대로다.

무엇을 만드는가
    0) 전원 인입 스웰 — 낮은 사인이 55→110Hz 로 올라오며 '깨어나는' 느낌.
    1) 상승 3음 아르페지오 — F#4 → A#4 → C#5 (F# 장3화음). 배음 3개를 섞고
       지수 감쇠를 씌워 종(bell) 같은 음색을 만든다.
    2) 마무리 여운 — 3음을 함께 짧게 울려 잔향처럼 닫는다.

    포맷은 기존 horn.wav 와 같게 맞춘다(mono / 16bit / 44.1kHz). 브라우저
    <audio> 가 그대로 받는다.

사용
    python tools/make_startup_chime.py                 # static/audio/startup.wav 생성
    python tools/make_startup_chime.py --out /tmp/a.wav
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).resolve().parent.parent / "static" / "audio" / "startup.wav"

RATE = 44100
PEAK = 0.89              # 최종 정규화 목표(-1.0 여유를 남겨 클리핑을 피한다)

# F# 장3화음 — 상승 아르페지오. (시작초, 주파수Hz, 지속초, 세기)
NOTES = [
    (0.22, 369.99, 1.15, 1.00),   # F#4
    (0.42, 466.16, 1.05, 0.92),   # A#4
    (0.62, 554.37, 1.30, 0.86),   # C#5
]
# 종 같은 음색 — 배음 비율(1배·2배·3배)과 각 세기.
PARTIALS = [(1.0, 1.00), (2.0, 0.38), (3.0, 0.16)]
TAIL_AT, TAIL_LEN = 1.05, 0.85    # 마무리 여운
TOTAL = 2.05


def env(t: float, dur: float, attack: float = 0.006) -> float:
    """5~6ms 페이드인(클릭 방지) + 지수 감쇠."""
    if t < 0 or t > dur:
        return 0.0
    a = t / attack if t < attack else 1.0
    return a * math.exp(-3.2 * t / dur)


def render() -> list[float]:
    n = int(TOTAL * RATE)
    buf = [0.0] * n

    # 0) 전원 인입 스웰 — 55Hz 에서 110Hz 로 부드럽게 올라온다.
    sw_len = 0.55
    for i in range(int(sw_len * RATE)):
        t = i / RATE
        f = 55.0 + (110.0 - 55.0) * (t / sw_len)
        # 위상은 주파수를 적분해 얻는다(선형 스윕이므로 평균 주파수 × t).
        ph = 2 * math.pi * (55.0 * t + (110.0 - 55.0) * t * t / (2 * sw_len))
        shape = math.sin(math.pi * t / sw_len) ** 1.5      # 들어오고 나가는 종 모양
        buf[i] += 0.42 * shape * math.sin(ph)

    # 1) 상승 3음
    for start, freq, dur, amp in NOTES:
        off = int(start * RATE)
        for i in range(int(dur * RATE)):
            if off + i >= n:
                break
            t = i / RATE
            e = env(t, dur)
            if e <= 0.0:
                continue
            s = sum(g * math.sin(2 * math.pi * freq * mult * t) for mult, g in PARTIALS)
            buf[off + i] += 0.30 * amp * e * s

    # 2) 마무리 여운 — 3음을 함께, 아주 작게.
    off = int(TAIL_AT * RATE)
    for i in range(int(TAIL_LEN * RATE)):
        if off + i >= n:
            break
        t = i / RATE
        e = env(t, TAIL_LEN)
        s = sum(math.sin(2 * math.pi * f * t) for _, f, _, _ in NOTES)
        buf[off + i] += 0.075 * e * s

    # 전체 페이드아웃 — 끝을 0 으로 닫아 재생 종료 시 툭 끊기는 소리를 막는다.
    fade = int(0.12 * RATE)
    for i in range(fade):
        buf[n - fade + i] *= 1.0 - i / fade

    peak = max(abs(v) for v in buf) or 1.0
    return [v * PEAK / peak for v in buf]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    samples = render()
    frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767)) for v in samples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    print(f"{args.out.name} · mono/16bit/{RATE}Hz · {len(samples) / RATE:.2f}s · "
          f"{args.out.stat().st_size:,}B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
