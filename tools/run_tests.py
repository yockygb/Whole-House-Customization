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
    test_tmp = ROOT / 'work' / 'test-temp'
    test_tmp.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(test_tmp), TMP=str(test_tmp), TMPDIR=str(test_tmp))
    failed = []
    with tempfile.TemporaryDirectory(prefix='quotation-tests-', dir=test_tmp) as tmp:
        base_env = dict(os.environ, TEMP=str(test_tmp), TMP=str(test_tmp), TMPDIR=str(test_tmp),
                        PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get('PYTHONPATH', ''),
                        PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
        for path in files:
            print('\n=== ' + path.name + ' ===', flush=True)
            with tempfile.TemporaryDirectory(prefix=path.stem + '-', dir=tmp) as case_tmp:
                env = dict(base_env,
                           VOUGUER_NEXT_DATA_DIR=str(Path(case_tmp) / 'data'),
                           VOUGUER_NEXT_EXPORT_DIR=str(Path(case_tmp) / 'exports'))
                result = subprocess.run([sys.executable, str(path)], cwd=ROOT, env=env)
            if result.returncode:
                failed.append(path.name)
    if failed:
        print('\nFailed test modules: ' + ', '.join(failed), flush=True)
        return 1
    print('\nAll %d test modules passed.' % len(files), flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
