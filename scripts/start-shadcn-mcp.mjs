import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// shadcn's MCP tools resolve registries from process.cwd(), not just --cwd.
const cwd = fileURLToPath(new URL('../Orbitium/frontend/', import.meta.url))
const windows = process.platform === 'win32'
const child = spawn(
  windows ? (process.env.ComSpec || 'cmd.exe') : 'npx',
  windows ? ['/d', '/s', '/c', 'npx -y shadcn@latest mcp'] : ['-y', 'shadcn@latest', 'mcp'],
  { cwd, stdio: 'inherit' },
)
child.on('error', (error) => { console.error(error); process.exitCode = 1 })
child.on('exit', (code) => { process.exitCode = code ?? 1 })
