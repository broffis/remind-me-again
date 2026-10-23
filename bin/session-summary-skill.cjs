#!/usr/bin/env node

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const usage = `Usage: session-summary-skill <install|update|uninstall> [--skills-dir <directory>]
       session-summary-skill setup-mcp [--cwd <directory>] [--skills-dir <directory>] [--approve] [--dry-run]

Installs the bundled Copilot skill using Python 3.9+ on macOS or Linux.
Install/update never change automation settings.
setup-mcp explicitly enables project MCP autosave using the installed skill.
--approve saves only this repository's checkpoint tool permission; close Copilot first.
`;

function main(args) {
  if (args.length === 1 && ['--help', '-h'].includes(args[0])) {
    process.stdout.write(usage);
    return 0;
  }

  const [action, ...options] = args;
  const setup = action === 'setup-mcp';
  const validAction = ['install', 'update', 'uninstall', 'setup-mcp'].includes(action);
  let validOptions = options.length === 0 || (
    options.length === 2 && options[0] === '--skills-dir'
    && options[1].length > 0 && !options[1].startsWith('-')
  );
  let skillsDirectory = path.join(require('node:os').homedir(), '.copilot', 'skills');
  const setupOptions = [];
  if (setup) {
    validOptions = true;
    const seen = new Set();
    for (let i = 0; i < options.length; i++) {
      const option = options[i];
      if (seen.has(option)) { validOptions = false; break; }
      seen.add(option);
      if (['--approve', '--dry-run'].includes(option)) {
        setupOptions.push(option);
      } else if (['--cwd', '--skills-dir'].includes(option)
        && options[i + 1] && !options[i + 1].startsWith('-')) {
        const value = options[++i];
        if (option === '--skills-dir') skillsDirectory = path.resolve(value);
        else setupOptions.push(option, value);
      } else { validOptions = false; break; }
    }
  }
  if (!validAction || !validOptions) {
    process.stderr.write(usage);
    return 2;
  }
  if (!['darwin', 'linux'].includes(process.platform)) {
    process.stderr.write('Requires Python 3.9+ on macOS or Linux.\n');
    return 1;
  }

  const installer = setup
    ? path.join(skillsDirectory, 'session-summary', 'scripts', 'setup_mcp.py')
    : path.resolve(__dirname, '..', 'install.py');
  if (setup && !require('node:fs').existsSync(installer)) {
    process.stderr.write('Install/update the skill before running setup-mcp.\n');
    return 1;
  }
  const pythonArgs = ['-B', installer];
  if (!setup && action !== 'install') {
    pythonArgs.push(`--${action}`);
  }
  pythonArgs.push(...(setup ? setupOptions : options));
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
