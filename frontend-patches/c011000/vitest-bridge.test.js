import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from 'vitest'

test('C011000/M20 diagnostics and D020100 safe-resume real-runtime scenarios', () => {
  const directory = process.env.C011000_PATCH_DIR
  if (!directory) throw new Error('C011000_PATCH_DIR must point to the reviewed patch directory')
  const scripts = ['controlled.test.mjs', 'initialization.test.mjs', 'resume.test.mjs', 'real-runtime.test.mjs']
    .map(name => resolve(directory, name))
  const output = execFileSync(process.execPath, ['--experimental-vm-modules', '--test', ...scripts], {
    encoding: 'utf8', env: { ...process.env, C011100_FRONTEND_ROOT: process.cwd() },
  })
  expect(output).toContain('# fail 0')
  expect(output).toContain('# skipped 0')
}, 60000)
