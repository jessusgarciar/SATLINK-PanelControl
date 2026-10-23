// Synthetic HTTP/WebSocket only. No broker, hardware or real backend is contacted.
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { chromium } from 'playwright'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'

process.env.VITE_DATA_SOURCE = 'live'
process.env.VITE_MISSION_ID = 'synthetic-commands-ui'
process.env.VITE_DEMO_PREDICTION = 'local'
const root = fileURLToPath(new URL('../', import.meta.url))
const server = await createServer({ root, server: { host: '127.0.0.1', port: 5191, strictPort: true, open: false } })
const fixture = await new DemoMissionGateway().load(new AbortController().signal)
fixture.mission = { ...fixture.mission, id: 'synthetic-commands-ui', name: 'Heltec SINTÉTICA',
  startedAt: null, phase: 'unknown', staleAfterSeconds: 21900 }
fixture.telemetry = fixture.telemetry.map((sample) => ({ ...sample, missionId: fixture.mission.id }))
fixture.prediction = null
fixture.permissions = { canCommand: true, canPredict: false }
fixture.csrfToken = 'synthetic-csrf'
fixture.commandSettings = { enabled: true, supportedTypes: ['START_MISSION', 'PING', 'STATUS', 'TELEMETRY'],
  reason: null, uplinkIntervalSeconds: 21600 }
let browser
try {
  await server.listen()
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === 'win32' ? 'msedge' : 'chromium'), headless: true })
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' })
  let socket
  let posts = 0
  let snapshot = structuredClone(fixture)
  await context.routeWebSocket(/\/api\//, (connection) => { socket = connection })
  await context.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.hostname !== '127.0.0.1') return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    if (url.pathname.endsWith('/dashboard')) return route.fulfill({ json: snapshot })
    if (url.pathname.endsWith('/commands') && request.method() === 'POST') {
      posts++
      const body = request.postDataJSON()
      assert.equal(body.type, 'START_MISSION')
      assert.equal(request.headers()['idempotency-key'], body.clientRequestId)
      assert.equal(request.headers()['x-csrf-token'], 'synthetic-csrf')
      const command = { id: crypto.randomUUID(), missionId: fixture.mission.id, ...body, status: 'pending',
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
        evidence: 'Solicitud SINTÉTICA pendiente de ejecución.', simulated: false }
      snapshot.commands = [command]
      return route.fulfill({ status: 202, json: command })
    }
    return route.fulfill({ status: 404, json: { detail: 'Synthetic test: endpoint unavailable' } })
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('http://127.0.0.1:5191', { waitUntil: 'networkidle' })
  const start = page.getByRole('button', { name: 'Iniciar misión', exact: true })
  await start.waitFor()
  assert.equal(await start.isEnabled(), true)
  assert.equal(await page.getByRole('button', { name: /Baliza/ }).count(), 0)
  assert.equal(await page.getByRole('button', { name: /RELEASE/ }).isDisabled(), true)
  await start.click()
  const dialog = page.getByRole('dialog', { name: 'Confirmar inicio de misión' })
  await dialog.waitFor()
  assert.equal(posts, 0)
  await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
  assert.equal(posts, 0)
  await start.click()
  await dialog.getByRole('button', { name: 'Confirmar inicio', exact: true }).click()
  const pending = page.getByRole('button', { name: 'Inicio solicitado', exact: true })
  await pending.waitFor()
  assert.equal(await pending.isDisabled(), true)
  assert.equal(posts, 1)
  assert.equal(snapshot.mission.startedAt, null)
  const watchdog = page.locator('.data-card').filter({ has: page.getByRole('heading', { name: 'Watchdog', exact: true }) }).locator('.data-value')
  assert.equal((await watchdog.textContent()).trim(), '—')
  await page.getByText('Solicitud SINTÉTICA pendiente de ejecución.', { exact: true }).waitFor()
  snapshot.mission = { ...snapshot.mission, startedAt: new Date().toISOString(), updatedAt: new Date().toISOString() }
  socket.send(JSON.stringify({ type: 'mission', data: snapshot.mission }))
  await page.getByRole('button', { name: 'Misión iniciada', exact: true }).waitFor()
  assert.notEqual((await watchdog.textContent()).trim(), '—')
  assert.equal(await page.getByRole('button', { name: 'Misión iniciada', exact: true }).isDisabled(), true)
  // With no profile the controls explain why they are unavailable.
  snapshot = structuredClone(fixture)
  snapshot.permissions.canCommand = false
  snapshot.commandSettings = { enabled: false, supportedTypes: [], reason: 'Pendiente de protocolo Heltec SINTÉTICO', uplinkIntervalSeconds: 21600 }
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByText('Pendiente de protocolo Heltec SINTÉTICO', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Iniciar misión', exact: true }).isDisabled(), true)
  assert.equal(await page.getByRole('button', { name: 'PING', exact: true }).isDisabled(), true)
  assert.equal(posts, 1)
  assert.deepEqual(errors, [])
  console.log('PASS · mobile command confirmation, pending start, confirmed start, disabled firmware, no duplicate POST, no browser errors')
  await context.close()
} finally {
  await browser?.close()
  await server.close()
}
