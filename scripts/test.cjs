// SPDX-License-Identifier: BSD-3-Clause
const { spawnSync } = require('node:child_process');
const { join } = require('node:path');

const root = join(__dirname, '..');
const python = process.platform === 'win32' ? 'python' : 'python3';
const commands = [
  [python, '-m', 'unittest', 'discover', '-s', 'tests'],
  [process.execPath, join(__dirname, 'import-release.cjs'), '--check'],
];

for (const [command, ...args] of commands) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' });
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) {
    process.exitCode = result.status ?? 1;
    break;
  }
}
