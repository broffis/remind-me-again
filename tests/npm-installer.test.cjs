const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { mkdtempSync, readFileSync, existsSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const cli = path.join(root, 'bin/session-summary-skill.cjs');

function run(args, options = {}) {
  return spawnSync(process.execPath, [cli, ...args], {
    encoding: 'utf8',
    ...options,
  });
}

test('help and invalid arguments do not invoke Python', () => {
  const env = { ...process.env, PATH: '' };
  assert.equal(run(['--help'], { env }).status, 0);
  for (const args of [
    [], ['unknown'], ['install', '--update'], ['install', '--skills-dir'],
    ['setup-mcp', '--cwd'], ['setup-mcp', '--approve', '--approve'],
    ['setup-mcp', '--unknown'],
  ]) {
    const result = run(args, { env });
    assert.equal(result.status, 2);
    assert.match(result.stderr, /Usage:/);
  }
});

test('missing Python produces an actionable error', () => {
  const result = run(['install'], { env: { ...process.env, PATH: '' } });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Python 3.9/);
});

test('install, explicit update, and uninstall share the Python installer', () => {
  const temporary = mkdtempSync(path.join(tmpdir(), 'session-summary-npm-'));
  try {
    const skills = path.join(temporary, 'skills with spaces');
    const args = ['--skills-dir', skills];
    assert.equal(run(['install', ...args]).status, 0);
    const destination = path.join(skills, 'session-summary');
    assert.ok(existsSync(path.join(destination, 'scripts/autosave.py')));
    const duplicate = run(['install', ...args]);
    assert.equal(duplicate.status, 1);
    assert.match(duplicate.stderr, /already exists/);
    assert.equal(run(['update', ...args]).status, 0);
    assert.equal(run(['uninstall', ...args, '--cwd', temporary]).status, 0);
    assert.equal(existsSync(destination), false);
  } finally {
    rmSync(temporary, { recursive: true });
  }
});

test('npm tarball contains every helper and can install outside the checkout', () => {
  const temporary = mkdtempSync(path.join(tmpdir(), 'session-summary-pack-'));
  try {
    const packed = spawnSync('npm', [
      'pack', '--json', '--ignore-scripts', '--pack-destination', temporary,
    ], { cwd: root, encoding: 'utf8' });
    assert.equal(packed.status, 0, packed.stderr);
    const [manifest] = JSON.parse(packed.stdout);
    const files = manifest.files.map((file) => file.path);
    for (const filename of [
      'install.py', 'bin/session-summary-skill.cjs', 'session-summary/SKILL.md',
      'session-summary/scripts/storage.py', 'session-summary/scripts/save_summary.py',
      'session-summary/scripts/rollup.py', 'session-summary/scripts/retrieval.py',
      'session-summary/scripts/autosave.py', 'LICENSE', 'README.md',
      'session-summary/scripts/checkpoint_mcp.py', 'session-summary/scripts/setup_mcp.py',
    ]) {
      assert.ok(files.includes(filename), `Missing ${filename}`);
    }
    assert.ok(files.every((file) => !/tests\/|\.DS_Store|__pycache__|^dist\//.test(file)));
    const extracted = spawnSync('tar', [
      '-xzf', path.join(temporary, manifest.filename), '-C', temporary,
    ], { encoding: 'utf8' });
    assert.equal(extracted.status, 0, extracted.stderr);
    const skills = path.join(temporary, 'installed');
    const installed = spawnSync(process.execPath, [
      path.join(temporary, 'package/bin/session-summary-skill.cjs'),
      'install', '--skills-dir', skills,
    ], { cwd: temporary, encoding: 'utf8' });
    assert.equal(installed.status, 0, installed.stderr);
    assert.equal(
      readFileSync(path.join(skills, 'session-summary/SKILL.md'), 'utf8'),
      readFileSync(path.join(root, 'session-summary/SKILL.md'), 'utf8'),
    );
  } finally {
    rmSync(temporary, { recursive: true });
  }
});

test('setup-mcp uses the installed helper and supports a no-write preview', () => {
  const temporary = mkdtempSync(path.join(tmpdir(), 'session-summary-setup-'));
  try {
    const skills = path.join(temporary, 'skills');
    assert.equal(run(['setup-mcp', '--skills-dir', skills]).status, 1);
    assert.equal(run(['install', '--skills-dir', skills]).status, 0);
    const repo = path.join(temporary, 'project');
    assert.equal(spawnSync('git', ['init', '-q', repo]).status, 0);
    const result = run([
      'setup-mcp', '--skills-dir', skills, '--cwd', repo, '--dry-run',
    ], { env: { ...process.env, HOME: temporary, COPILOT_HOME: path.join(temporary, '.copilot') } });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Would update/);
    assert.match(result.stdout, /No tool approval granted/);
  } finally {
    rmSync(temporary, { recursive: true });
  }
});

test('uninstall accepts cleanup preview options and does not delete the skill', () => {
  const temporary = mkdtempSync(path.join(tmpdir(), 'session-summary-uninstall-'));
  try {
    const skills = path.join(temporary, 'skills');
    assert.equal(run(['install', '--skills-dir', skills]).status, 0);
    const result = run([
      'uninstall', '--skills-dir', skills, '--cwd', temporary, '--global', '--dry-run',
    ], { env: { ...process.env, HOME: temporary, COPILOT_HOME: path.join(temporary, '.copilot') } });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Would remove\/update/);
    assert.ok(existsSync(path.join(skills, 'session-summary/SKILL.md')));
  } finally {
    rmSync(temporary, { recursive: true });
  }
});
