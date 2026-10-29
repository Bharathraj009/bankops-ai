// Local preview PID 1: normalize only our requested shutdown, preserve failures.
import { spawn } from 'node:child_process'
import { constants } from 'node:os'
import { pathToFileURL } from 'node:url'

export function exitStatus(code, signal, requested) {
  const signalCode = (name) => 128 + (constants.signals[name] ?? 0)
  if (
    requested &&
    (code === 0 || signal === requested || code === signalCode(requested))
  )
    return 0
  return code ?? (signal ? signalCode(signal) : 1)
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const child = spawn(
    process.execPath,
    [
      'node_modules/vite/bin/vite.js',
      'preview',
      '--config',
      'preview.config.ts',
      '--host',
      '0.0.0.0',
      '--port',
      '5173',
      '--strictPort',
    ],
    { stdio: 'inherit' },
  )
  let requested
  for (const signal of ['SIGTERM', 'SIGINT']) {
    process.once(signal, () => {
      requested = signal
      child.kill(signal)
    })
  }
  child.once('error', () => {
    console.error('Local frontend process could not be started')
    process.exitCode = 1
  })
  child.once('exit', (code, signal) => {
    process.exitCode = exitStatus(code, signal, requested)
  })
}
