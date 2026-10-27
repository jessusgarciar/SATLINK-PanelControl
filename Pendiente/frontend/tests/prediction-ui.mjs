import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { chromium } from 'playwright'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'

process.env.VITE_DATA_SOURCE = 'live'
process.env.VITE_MISSION_ID = 'satlink-demo'
process.env.VITE_API_BASE_URL = '/api/v1'
const root = fileURLToPath(new URL('../', import.meta.url))
const output = fileURLToPath(new URL('../../.local/ui-evidence/prediction-workflow/', import.meta.url))
await mkdir(output, { recursive: true })
const demo = new DemoMissionGateway()
const data = await demo.load(new AbortController().signal)
data.prediction = null
// Synthetic transport fixture: no physical telemetry or provider call is involved.
data.predictionHistory = []
data.permissions.canPredict = true
data.csrfToken = 'ui-test'
data.predictionSettings = { enabled: true, launchAltitudeReference: 'MSL', gpsAltitudeReference: 'MSL', nextAllowedAt: null }
data.mission.phase = 'unknown'
const latest = data.telemetry.at(-1)
latest.receivedAt = new Date().toISOString()
latest.device = { ...latest.device, gpsFix: true }
let fail = false
let sequence = 0
const calls = []
const errors = []
const server = await createServer({ root, server: { host: '127.0.0.1', port: 5192, strictPort: true, open: false } })
let browser
try {
  await server.listen()
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const context = await browser.newContext({ viewport: { width: 1366, height: 1000 }, timezoneId: 'America/Mexico_City' })
  await context.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.hostname !== '127.0.0.1') return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    if (url.pathname.endsWith('/dashboard')) return route.fulfill({ json: data })
    if (url.pathname.endsWith('/telemetry/window')) return route.fulfill({ json: { from: null, to: new Date().toISOString(), total: 0, series: [], track: [] } })
    if (url.pathname.endsWith('/predictions') && route.request().method() === 'POST') {
      const p = route.request().postDataJSON()
      calls.push(p)
      if (fail) {
        data.predictionSettings.nextAllowedAt = new Date(Date.now() + 3000).toISOString()
        return route.fulfill({ status: 502, json: { detail: 'El servicio de predicción respondió HTTP 402. Se conserva la predicción anterior.' } })
      }
      const fixture = await demo.predict({ ...p, ascentWindDirection: 45, ascentWindMs: 8, descentWindDirection: 120, descentWindMs: 5 })
      const origin = p.mode === 'planned' ? p.launch : { latitude: latest.latitude, longitude: latest.longitude, altitudeM: latest.altitudeGpsM }
      const result = { ...fixture, source: 'tawhiri', id: `ui-${++sequence}`, parameters: p,
        generatedAt: new Date(Date.now() + sequence * 10).toISOString(),
        context: { mode: p.mode, origin, originAt: p.launchDatetime ?? latest.receivedAt, telemetryId: p.mode === 'ascending' ? latest.id : null, dataset: '2026102700', altitudeReference: 'MSL' } }
      data.prediction = result
      data.predictionHistory = [result, ...data.predictionHistory].slice(0, 4)
      return route.fulfill({ json: result })
    }
    return route.fulfill({ json: { items: [], nextCursor: null } })
  })
  await context.routeWebSocket(/\/api\//, ws => {
    ws.send(JSON.stringify({ type: 'heartbeat' }))
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('http://127.0.0.1:5192', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /Recuperación/ }).click()
  const view = page.getByRole('dialog', { name: 'Rastreo y predicción', exact: true })
  await view.locator('.leaflet-host').waitFor()
  assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()), '#ffffff', 'Pendiente keeps its light palette')
  const planned = view.getByRole('button', { name: /^Planificación Antes/ })
  const ascending = view.getByRole('button', { name: /^Ascenso Durante/ })
  const up = view.getByLabel('Velocidad de ascenso · m/s', { exact: true })
  const down = view.getByLabel('Velocidad de descenso · m/s', { exact: true })
  const submit = view.locator('.prediction-calculate')
  assert.equal(await view.getByText('Planificación independiente', { exact: false }).count(), 0)
  await submit.click()
  await view.locator('.prediction-used').waitFor()
  const originalResult = (await view.locator('.prediction-result-metrics .definition').allTextContents()).slice(0, 2)
  await up.fill('6')
  await view.getByText('Cambios pendientes de calcular', { exact: true }).waitFor()
  assert.deepEqual((await view.locator('.prediction-result-metrics .definition').allTextContents()).slice(0, 2), originalResult)
  await submit.click()
  await view.getByRole('button', { name: 'Comparar con anterior', exact: true }).waitFor()
  assert.equal(calls[1].ascentRateMs, 6)
  assert.notEqual(data.predictionHistory[0].landing.time, data.predictionHistory[1].landing.time)
  await view.getByRole('button', { name: 'Comparar con anterior', exact: true }).click()
  await view.locator('.prediction-comparison').waitFor()
  await down.fill('8')
  await submit.click()
  assert.equal(calls[2].descentRateMs, 8)
  const savedPlan = data.prediction.id
  await ascending.click()
  assert.equal(await view.getByLabel('Fecha y hora de lanzamiento').count(), 0)
  assert.equal(await view.locator('.prediction-used').count(), 0)
  await up.fill('7')
  await submit.click()
  await view.locator('.prediction-used').waitFor()
  assert.equal(calls[3].mode, 'ascending')
  assert.equal('launchDatetime' in calls[3], false)
  await planned.click()
  assert.equal(await up.inputValue(), '6')
  assert.equal(await down.inputValue(), '8')
  assert.match(await view.locator('.prediction-used').textContent(), /6.0 m\/s/)
  assert.equal(data.predictionHistory.some(p => p.id === savedPlan), true)
  fail = true
  await up.fill('8')
  await submit.click()
  await view.getByRole('alert').filter({ hasText: 'HTTP 402' }).waitFor()
  await page.waitForTimeout(200)
  assert.match(await view.locator('.prediction-used').textContent(), /6.0 m\/s/)
  assert.equal(await submit.isDisabled(), true)
  await page.waitForTimeout(3200)
  assert.equal(await submit.isEnabled(), true)
  await view.evaluate(el => { el.scrollTop = 0 })
  await page.screenshot({ path: `${output}/desktop-planning.png` })
  await view.getByRole('button', { name: 'Cerrar diálogo' }).click()
  await page.getByRole('button', { name: /Recuperación/ }).click()
  assert.equal(await up.inputValue(), '8', 'draft survives closing the workspace')
  await ascending.click()
  assert.equal(await up.inputValue(), '7', 'ascent draft stays separate')
  await view.evaluate(el => { el.scrollTop = 0 })
  await page.screenshot({ path: `${output}/desktop-ascent.png` })
  for (const width of [320, 393, 852, 1366]) {
    await page.setViewportSize({ width, height: 900 })
    await planned.click()
    assert.equal(await view.evaluate(el => el.scrollWidth > el.clientWidth + 1), false, `no overflow at ${width}`)
    await view.evaluate(el => { el.scrollTop = 0 })
    await page.screenshot({ path: `${output}/planning-${width}.png` })
  }
  // A reload restores saved results of both modes from the server history.
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /Recuperación/ }).click()
  await view.locator('.prediction-used').waitFor()
  await ascending.click()
  await view.locator('.prediction-used').waitFor()
  assert.match(await view.locator('.prediction-used').textContent(), /7.0 m\/s/)
  latest.receivedAt = new Date(Date.now() - 3600000).toISOString()
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /Recuperación/ }).click()
  await ascending.click()
  const alternative = view.getByRole('button', { name: 'Usar Planificación mientras llega GPS', exact: true })
  await alternative.waitFor()
  assert.equal(await submit.isDisabled(), true, 'old GPS cannot be treated as a live ascent')
  await alternative.click()
  assert.equal(await planned.getAttribute('aria-pressed'), 'true')
  assert.deepEqual(errors, [])
  await writeFile(`${output}/report.json`, JSON.stringify({ environment: 'Synthetic API responses, no real provider calls', calls, checks: ['separate modes and drafts', 'velocity requests and changed synthetic trajectories', 'previous-result comparison', 'failure preserves route and shows upstream 402', 'countdown unlocks', 'drafts survive close', 'results survive reload', '320/393/852/1366 widths'], errors }, null, 2))
  console.log('Prediction UX checks passed; synthetic API fixtures only.')
} finally {
  await browser?.close()
  await server.close()
}
