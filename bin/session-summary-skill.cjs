#!/usr/bin/env node

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const usage = `Usage: session-summary-skill <install|update|uninstall> [--skills-dir <directory>]

Installs the bundled Copilot skill using Python 3.9+ on macOS or Linux.
Automation settings are never changed.
`;

function main(args) {
  if (args.length === 1 && ['--help', '-h'].includes(args[0])) {
    process.stdout.write(usage);
    return 0;
  }

  const [action, ...options] = args;
  const validAction = ['install', 'update', 'uninstall'].includes(action);
  const validOptions = options.length === 0 || (
    options.length === 2 && options[0] === '--skills-dir'
    && options[1].length > 0 && !options[1].startsWith('-')
  );
  if (!validAction || !validOptions) {
    process.stderr.write(usage);
    return 2;
  }
  if (!['darwin', 'linux'].includes(process.platform)) {
    process.stderr.write('Requires Python 3.9+ on macOS or Linux.\n');
    return 1;
  }

  const installer = path.resolve(__dirname, '..', 'install.py');
  const pythonArgs = ['-B', installer];
  if (action !== 'install') {
    pythonArgs.push(`--${action}`);
  }
  pythonArgs.push(...options);
  const result = spawnSync('python3', pythonArgs, { stdio: 'inherit' });
  if (result.error) {
    const message = result.error.code === 'ENOENT'
      ? 'Python 3.9+ is required. Install it and ensure python3 is on PATH.'
      : `Could not start Python: ${result.error.message}`;
    process.stderr.write(`${message}\n`);
    return 1;
  }
  if (result.signal) {
    process.stderr.write(`Installer interrupted by ${result.signal}.\n`);
    return 1;
  }
  return result.status;
}

process.exitCode = main(process.argv.slice(2));
