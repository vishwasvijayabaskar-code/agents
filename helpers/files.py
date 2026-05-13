import os
import re
from pathlib import Path

def _write_files(content: str, output_dir: str) -> list[str]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    written = []

    # Try filename headers: **filename.ext** or ### filename.ext
    named_pattern = re.compile(
        r'(?:\*\*([^*\n]+\.\w+)\*\*|###\s+([^\n]+\.\w+))\s*\n```(?:\w+)?\n(.*?)```',
        re.DOTALL
    )
    matches = list(named_pattern.finditer(content))

    if matches:
        for m in matches:
            filename = (m.group(1) or m.group(2)).strip()
            code = m.group(3)
            path = os.path.join(output_dir, filename)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                f.write(code)
            written.append(filename)
    else:
        lang_map = {
            'html': 'index.html', 'css': 'styles.css',
            'javascript': 'script.js', 'js': 'script.js',
            'python': 'output.py', 'py': 'output.py',
            'typescript': 'output.ts', 'ts': 'output.ts',
        }
        lang_pattern = re.compile(r'```(\w+)\n(.*?)```', re.DOTALL)
        seen = set()
        for m in lang_pattern.finditer(content):
            lang = m.group(1).lower()
            filename = lang_map.get(lang, f'output.{lang}')
            if filename in seen:
                continue
            seen.add(filename)
            path = os.path.join(output_dir, filename)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                f.write(m.group(2))
            written.append(filename)

    return written
