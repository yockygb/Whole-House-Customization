"""Run each test module in a separate process with disposable business data."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    files = sorted((ROOT / 'tests').glob('test_*.py'))
    if not files:
        raise SystemExit('No test modules found')
    with tempfile.TemporaryDirectory(prefix='whole-house-customization-tests-') as tmp:
        env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                   PYTHONDONTWRITEBYTECODE='1',
                   WHOLE_HOUSE_CUSTOMIZATION_DATA_DIR=str(Path(tmp) / 'data'),
                   WHOLE_HOUSE_CUSTOMIZATION_EXPORT_DIR=str(Path(tmp) / 'exports'))
        for path in files:
            print('\n=== ' + path.name + ' ===', flush=True)
            result = subprocess.run([sys.executable, str(path)], cwd=ROOT, env=env)
            if result.returncode:
                return result.returncode
    print('\nAll %d test modules passed.' % len(files), flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
