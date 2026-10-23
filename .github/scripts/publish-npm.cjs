// Permit retries after npm publication succeeds but asset upload fails.
const { spawnSync } = require('node:child_process');
const { name, version } = require('../../package.json');

const lookup = spawnSync('npm', ['view', `${name}@${version}`, 'version', '--json'], {
  encoding: 'utf8',
});
if (lookup.error) {
  throw lookup.error;
}
if (lookup.status === 0) {
  if (JSON.parse(lookup.stdout) !== version) {
    throw new Error('Registry returned an unexpected version.');
  }
  console.log(`${name}@${version} already exists; skipping immutable npm publication.`);
} else {
  const response = JSON.parse(lookup.stdout);
  if (response.error?.code !== 'E404') {
    process.stderr.write(lookup.stderr);
    throw new Error('Registry lookup failed; refusing to guess whether the version exists.');
  }
  const publish = spawnSync('npm', ['publish', '--access', 'public', '--provenance', '--ignore-scripts'], {
    stdio: 'inherit',
  });
  if (publish.error) {
    throw publish.error;
  }
  if (publish.signal) {
    throw new Error(`npm publish interrupted by ${publish.signal}.`);
  }
  process.exitCode = publish.status;
}
