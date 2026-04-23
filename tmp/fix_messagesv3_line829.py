from pathlib import Path

p = Path(r"frontend/src/features/conversation/components/v3/MessagesV3.tsx")
s = p.read_text(encoding="utf-8")

bad = "const hasStreamText = Boolean((streamingTextOverride ?? item.text ?? '').trim())`r`n  const messageSourceText =`r`n    streamingTextOverride ??`r`n    (isStreamingMessage && !hasStreamText ? 'Responding...' : (item.text ?? ''))"
good = "const hasStreamText = Boolean((streamingTextOverride ?? item.text ?? '').trim())\n  const messageSourceText =\n    streamingTextOverride ??\n    (isStreamingMessage && !hasStreamText ? 'Responding...' : (item.text ?? ''))"

if bad not in s:
    raise SystemExit("target snippet not found")

p.write_text(s.replace(bad, good, 1), encoding="utf-8")
print("patched")
