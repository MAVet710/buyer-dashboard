from pathlib import Path

path = Path("frontend/e2e/operator-zero-training.spec.ts")
source = path.read_text(encoding="utf-8")
old = '''      const message = error instanceof Error ? error.message : String(error);\n      if (/detached from the DOM|element is not attached|not stable/i.test(message)) return false;\n      throw error;\n'''
new = '''      const message = error instanceof Error ? error.message : String(error);\n      if (/detached from the DOM|element is not attached|not stable/i.test(message)) return false;\n      if (/Timeout .* exceeded|TimeoutError|locator\\.click: Timeout/i.test(message) && !(await actionable(locator))) return false;\n      throw error;\n'''
count = source.count(old)
if count != 1:
    raise SystemExit(f"Expected exactly one transient-action block, found {count}.")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
