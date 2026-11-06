"""Reproduce the core extraction; not used when running a station.

Keep original runtime functions, removing only HTTP transport and CLI startup.
The station-specific replacements are explicit in runtime.py.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1])
target = root / 'upstream'
target.mkdir(exist_ok=True)
hashes = {}
for name in ('eval_gui.py', 'eval_gui.html', 'record_evals.py', 'review_evals.py'):
    raw = (source / 'scripts' / name).read_bytes()
    (target / name).write_bytes(raw)
    hashes[name] = hashlib.sha256(raw).hexdigest()
(target / 'source.json').write_text(json.dumps({'source': str(source), 'sha256': hashes}, indent=2), encoding='utf-8')
code = (target / 'eval_gui.py').read_text(encoding='utf-8')
lines = code.splitlines(keepends=True)
remove = {'index', 'thumb', 'video', 'ws', 'lifespan', 'main', 'poll_server'}
parts = ['# Derived from upstream/eval_gui.py; see tools/derive_upstream.py.\n']
for n in ast.parse(code).body:
    if isinstance(n, (ast.Import, ast.ImportFrom)):
        names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module]
        if any(x and (x == 'uvicorn' or x.startswith('fastapi')) for x in names):
            continue
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in remove:
        continue
    if isinstance(n, ast.If) and '__name__' in ast.get_source_segment(code, n.test):
        continue
    if isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == 'app' for x in n.targets):
        continue
    parts.append(''.join(lines[n.lineno-1:n.end_lineno]) + '\n\n')
core = ''.join(parts).replace('sys.path.insert(0, str(HERE))', 'sys.path.insert(0, str(HERE / "upstream"))')
core = core.replace('import record_evals  # noqa: E402', 'import record_evals  # noqa: E402')
core = core.replace("CAMS = rv.CAMS", 'class HTTPException(Exception):\n    def __init__(self, status_code, detail="Not found"):\n        super().__init__(detail)\n        self.status_code, self.detail = status_code, detail\n\nCAMS = rv.CAMS')
(root / 'upstream_core.py').write_text(core, encoding='utf-8')
# The two nested f-strings require Python 3.12 upstream. Spell them equivalently for Franka 3.10.
review = (target / 'review_evals.py').read_text(encoding='utf-8')
review = '\n'.join(
    '            lines += ["file \'{}\'".format((src / cam / (format(row["frame"], "06d") + ".png")).resolve()), f"duration {max(d, .001):.6f}"]'
    if 'lines +=' in line and "row['frame']" in line else
    '        lines.append("file \'{}\'".format((src / cam / (format(rows[-1]["frame"], "06d") + ".png")).resolve()))'
    if 'lines.append' in line and "rows[-1]['frame']" in line else line
    for line in review.splitlines()) + '\n'
(root / 'review_evals.py').write_text(review, encoding='utf-8')
# Resolve adapted review before upstream's import path.
core = core.replace('sys.path.insert(0, str(HERE / "upstream"))', 'sys.path.append(str(HERE / "upstream"))')
core = core.replace("        S.set_run(phase='prompt')\n        with S.lock:", "        self.event.clear()\n        S.set_run(phase='prompt')\n        with S.lock:")
core = core.replace('        self.event.clear()\n        self.event.wait()', '        self.event.wait()')
(root / 'upstream_core.py').write_text(core, encoding='utf-8')
(root / 'eval_gui.html').write_bytes((target / 'eval_gui.html').read_bytes())
