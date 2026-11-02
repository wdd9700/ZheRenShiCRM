import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from 'vitest'

test('C011000 controlled resource and browser-adapter scenarios', () => {
  const directory = process.env.C011000_PATCH_DIR
  if (!directory) throw new Error('C011000_PATCH_DIR must point to the reviewed patch directory')
  const script = resolve(directory, 'controlled.test.mjs')
  const output = execFileSync(process.execPath, ['--experimental-vm-modules', '--test', script], { encoding: 'utf8' })
  expect(output).toContain('# fail 0')
}, 30000)
