import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

export default function setup() {
  const root = fileURLToPath(new URL('../../../', import.meta.url));
  const python = process.env.ERRORBARS_REPORT_PYTHON ?? join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const directory = mkdtempSync(join(tmpdir(), 'errorbars-reports-'));
  process.env.ERRORBARS_REPORT_FIXTURES = directory;
  try {
    execFileSync(python, [join(root, 'scripts/build_report_fixtures.py'), directory], { cwd: root, stdio: 'pipe' });
  } catch (error) {
    rmSync(directory, { recursive: true, force: true });
    throw error;
  }
  return () => rmSync(directory, { recursive: true, force: true });
}
