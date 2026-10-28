const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const filename = path.join(__dirname, '../.github/scripts/publish-npm.cjs');
const source = readFileSync(filename, 'utf8');

function execute(results) {
  const calls = [];
  const processStub = { stderr: { write() {} }, exitCode: undefined };
  const context = {
    require(name) {
      if (name === 'node:child_process') {
        return {
          spawnSync(...args) {
            calls.push(args);
            return results.shift();
          },
        };
      }
      return { name: 'remind-me-again', version: '0.1.0' };
    },
    console: { log() {} },
    process: processStub,
  };
  vm.runInNewContext(source, context, { filename });
  return { calls, exitCode: processStub.exitCode };
}

test('published versions are skipped for asset-upload retries', () => {
  const result = execute([{ status: 0, stdout: '"0.1.0"' }]);
  assert.equal(result.calls.length, 1);
});

test('only a registry E404 permits publishing', () => {
  const result = execute([
    { status: 1, stdout: '{"error":{"code":"E404"}}' },
    { status: 0 },
  ]);
  assert.equal(result.calls.length, 2);
  assert.equal(result.calls[1][1][0], 'publish');
  assert.ok(result.calls[1][1].includes('--provenance'));
  assert.equal(result.exitCode, 0);
});

test('lookup failures never attempt publication', () => {
  for (const response of [
    { status: 1, stdout: '{"error":{"code":"E401"}}', stderr: 'Unauthorized' },
    { status: 1, stdout: 'Network failure' },
    { error: new Error('Cannot run npm') },
    { status: 0, stdout: '"0.2.0"' },
  ]) {
    assert.throws(() => execute([response]));
  }
});

test('publish failures and interruptions are not reported as success', () => {
  const missing = { status: 1, stdout: '{"error":{"code":"E404"}}' };
  assert.equal(execute([missing, { status: 1 }]).exitCode, 1);
  assert.throws(() => execute([missing, { signal: 'SIGTERM' }]));
  assert.throws(() => execute([missing, { error: new Error('Spawn failed') }]));
});
