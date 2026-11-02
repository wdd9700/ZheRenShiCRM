import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from 'vitest'

test('C011000 controlled resource and browser-adapter scenarios', () => {
  const directory = process.env.C011000_PATCH_DIR
  if (!directory) throw new Error('C011000_PATCH_DIR must point to the reviewed patch directory')
  const scripts = ['controlled.test.mjs', 'initialization.test.mjs'].map(name => resolve(directory, name))
  const output = execFileSync(process.execPath, ['--experimental-vm-modules', '--test', ...scripts], { encoding: 'utf8' })
  expect(output).toContain('# fail 0')
}, 30000)

test('C011100 actual main and session with fixed real Vue/Pinia runtime', () => {
  const directory = process.env.C011000_PATCH_DIR
  if (!directory) throw new Error('C011000_PATCH_DIR must point to the reviewed patch directory')
  const script = resolve(directory, 'real-runtime.test.mjs')
  const output = execFileSync(process.execPath, ['--experimental-vm-modules', '--test', script], {
    encoding: 'utf8', env: { ...process.env, C011100_FRONTEND_ROOT: process.cwd() },
  })
  expect(output).toContain('# fail 0')
}, 30000)
