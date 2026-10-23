import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { chromium } from 'playwright'

// Isolated visual regression smoke test: demo only, no backend or external providers.
process.env.VITE_DATA_SOURCE = 'demo'
process.env.VITE_DEMO_PREDICTION = 'local'
const root = fileURLToPath(new URL('../', import.meta.url))
const output = fileURLToPath(new URL('../../.local/ui-evidence/', import.meta.url))
await mkdir(output, { recursive: true })
const server = await createServer({ root, server: { host: '127.0.0.1', port: 5188, strictPort: true, open: false } })
let browser
const errors = []
const report = { browser: '', environment: 'Windows/Edge or installed Chromium; Vite development; simulated telemetry; provider requests blocked', checks: [], frames: {} }
const capture = (page, name, fullPage = false) => page.screenshot({ path: `${output}/${name}.png`, fullPage })
async function frames(page) {
  return page.evaluate(() => new Promise(resolve => {
    const samples = []
    let previous
    const step = now => {
      if (previous !== undefined) samples.push(now - previous)
      previous = now
      if (samples.length < 180) requestAnimationFrame(step)
      else {
        samples.sort((a, b) => a - b)
        resolve({ samples: samples.length, medianMs: +samples[90].toFixed(2), p95Ms: +samples[171].toFixed(2), over34ms: samples.filter(value => value > 34).length })
      }
    }
    requestAnimationFrame(step)
  }))
}
try {
  await server.listen()
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === 'win32' ? 'msedge' : 'chromium'), headless: true })
  report.browser = browser.version()
  const context = await browser.newContext({ viewport: { width: 393, height: 852 }, isMobile: true, hasTouch: true, timezoneId: 'Asia/Tokyo' })
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    return url.hostname === '127.0.0.1' && !url.pathname.startsWith('/api') ? route.continue() : route.abort()
  })
  await context.routeWebSocket(/\/api\//, socket => socket.close({ code: 1008, reason: 'UI test: backend isolated' }))
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('http://127.0.0.1:5188', { waitUntil: 'networkidle', timeout: 90000 })
  await page.locator('.mission-summary').waitFor()
  await page.locator('.mission-map').first().waitFor()
  await page.waitForTimeout(800)
  assert.equal(await page.locator('.spotlight-card').count(), 0)
  assert.equal(await page.getByRole('navigation', { name: 'Secciones de misión' }).count(), 0)
  assert.equal(await page.locator('.mission-bottom-nav').count(), 0)
  assert.equal(await page.locator('.mission-summary').getByRole('meter').count(), 1)
  assert.equal(await page.locator('.mission-summary').getByRole('slider').count(), 0)
  assert.equal(await page.locator('.mission-aurora canvas').evaluate(canvas => canvas.getContext('webgl2')?.isContextLost()), false)
  report.frames.header = await frames(page)
  await capture(page, 'mobile-393')
  assert.equal(await page.getByRole('combobox', { name: 'Fuente de datos' }).count(), 0)
  assert.equal(await page.locator('.card-nav__content').getAttribute('inert'), '')

  const information = page.getByRole('button', { name: 'Información de misión', exact: true })
  for (const viewport of [{ width: 375, height: 812 }, { width: 1280, height: 800 }, { width: 852, height: 393 }]) {
    await page.setViewportSize(viewport)
    const brand = await page.locator('.card-nav__logo').boundingBox()
    const left = await information.boundingBox()
    const right = await page.locator('.card-nav__menu').boundingBox()
    assert.ok(left.x + left.width <= brand.x && brand.x + brand.width <= right.x, 'Header controls must not overlap')
    assert.ok(Math.abs(brand.x + brand.width / 2 - viewport.width / 2) < 2, 'Brand must remain centered')
  }
  await page.setViewportSize({ width: 393, height: 852 })
  await information.click()
  const infoDialog = page.getByRole('dialog', { name: 'Información de misión', exact: true })
  await infoDialog.waitFor()
  assert.equal(await infoDialog.locator('input').count(), 0, 'Information opens read-only')
  await capture(page, 'mobile-mission-information')
  await infoDialog.getByRole('button', { name: 'Editar parámetros' }).click()
  assert.equal(await infoDialog.getByLabel('Fecha y hora previstas de lanzamiento', { exact: true }).evaluate(el => document.activeElement === el), true)
  await infoDialog.getByText('Hora de Aguascalientes · UTC−06:00.', { exact: false }).waitFor()
  const latitudeInput = infoDialog.getByLabel('Latitud · °', { exact: true })
  const longitudeInput = infoDialog.getByLabel('Longitud · °', { exact: true })
  const originalLatitude = await latitudeInput.inputValue()
  const locationMap = infoDialog.getByRole('region', { name: 'Mapa del punto de lanzamiento' }).locator('.planning-map')
  await locationMap.waitFor()
  await locationMap.scrollIntoViewIfNeeded()
  let locationBox = await locationMap.boundingBox()
  await page.touchscreen.tap(locationBox.x + locationBox.width * .7, locationBox.y + locationBox.height * .4)
  await infoDialog.locator('.mission-map-feedback').filter({ hasText: 'Punto seleccionado:' }).waitFor()
  assert.notEqual(await latitudeInput.inputValue(), originalLatitude, 'Touch selects map coordinates')
  await capture(page, 'mobile-mission-information-map')
  await infoDialog.getByLabel('Ubicación de lanzamiento', { exact: true }).fill('Cambio descartado')
  await infoDialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
  assert.equal(await infoDialog.getByText('Cambio descartado', { exact: true }).count(), 0)
  await infoDialog.getByRole('button', { name: 'Editar parámetros' }).click()
  assert.equal(await latitudeInput.inputValue(), originalLatitude, 'Cancel discards map selection')
  await locationMap.waitFor()
  await locationMap.scrollIntoViewIfNeeded()
  locationBox = await locationMap.boundingBox()
  await page.touchscreen.tap(locationBox.x + locationBox.width * .65, locationBox.y + locationBox.height * .45)
  await infoDialog.locator('.mission-map-feedback').filter({ hasText: 'Punto seleccionado:' }).waitFor()
  const selectedLatitude = await latitudeInput.inputValue()
  const selectedLongitude = await longitudeInput.inputValue()
  await infoDialog.getByLabel('Altitud objetivo relativa · m', { exact: true }).fill('15001')
  await infoDialog.getByRole('button', { name: 'Guardar parámetros' }).click()
  assert.equal(await infoDialog.getByLabel('Altitud objetivo relativa · m', { exact: true }).getAttribute('aria-invalid'), 'true')
  await infoDialog.getByLabel('Altitud objetivo relativa · m', { exact: true }).fill('14000')
  await infoDialog.getByLabel('Ubicación de lanzamiento', { exact: true }).fill('Sitio de prueba UI')
  await infoDialog.getByLabel('Fecha y hora previstas de lanzamiento', { exact: true }).fill('2026-11-01T08:30')
  await capture(page, 'mobile-mission-information-edit')
  assert.equal(await infoDialog.evaluate(el => el.scrollWidth > el.clientWidth), false)
  await infoDialog.getByRole('button', { name: 'Guardar parámetros' }).click()
  await infoDialog.getByText('Parámetros simulados guardados para esta sesión.', { exact: true }).waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await information.evaluate(el => document.activeElement === el), true)
  await information.click()
  await infoDialog.getByText('Sitio de prueba UI', { exact: true }).waitFor()
  await infoDialog.getByText('Lanzamiento previsto · AGS', { exact: true }).waitFor()
  await infoDialog.getByRole('button', { name: 'Editar parámetros' }).click()
  assert.equal(await infoDialog.getByLabel('Fecha y hora previstas de lanzamiento', { exact: true }).inputValue(), '2026-11-01T08:30', 'AGS time is unchanged on a Tokyo device')
  assert.equal(await latitudeInput.inputValue(), selectedLatitude)
  assert.equal(await longitudeInput.inputValue(), selectedLongitude)
  await page.keyboard.press('Escape')
  report.checks.push('Mission information: centered header, touch map selection, cancel/save coordinates, fixed AGS time on Tokyo device, read-only identity, validation, reopen, Escape and focus restoration')

  const menu = page.locator('.card-nav__menu')
  await menu.click()
  await page.waitForTimeout(500)
  assert.equal(await menu.getAttribute('aria-expanded'), 'true')
  const source = page.getByRole('combobox', { name: 'Fuente de datos' })
  assert.equal(await source.inputValue(), 'demo')
  assert.equal(await page.getByRole('region', { name: 'Estado y fuente de misión' }).count(), 1)
  const statusBox = await page.locator('.mission-status-rail').boundingBox()
  const cardsBox = await page.locator('.card-nav__cards').boundingBox()
  assert.ok(statusBox.y + statusBox.height <= cardsBox.y, 'Mission controls must precede the navigation cards')
  await capture(page, 'mobile-menu')
  await page.getByRole('link', { name: 'Archivo y CSV', exact: true }).focus()
  await page.keyboard.press('Escape')
  assert.equal(await menu.getAttribute('aria-expanded'), 'false')
  assert.equal(await menu.evaluate(element => document.activeElement === element), true)
  assert.equal(await page.getByRole('combobox', { name: 'Fuente de datos' }).count(), 0)
  report.checks.push('Card Nav: controls at top, inert while closed, Escape and restored focus')

  await page.locator('#mission-map').scrollIntoViewIfNeeded()
  await page.waitForTimeout(800)
  const mapSwitch = page.getByRole('switch', { name: 'Mapa base' }).first()
  const initial = await mapSwitch.getAttribute('aria-checked')
  await mapSwitch.click()
  assert.notEqual(await mapSwitch.getAttribute('aria-checked'), initial)
  await mapSwitch.click()
  const box = await page.locator('.leaflet-host').first().boundingBox()
  await page.mouse.move(box.x + 120, box.y + 100)
  await page.mouse.down()
  await page.mouse.move(box.x + 170, box.y + 135, { steps: 15 })
  await page.mouse.up()
  const follow = page.locator('.map-toolbar button.map-control').first()
  assert.equal(await follow.getAttribute('aria-pressed'), 'false')
  await follow.click()
  await page.locator('.leaflet-control-zoom-in').first().click()
  report.frames.map = await frames(page)
  report.checks.push('No main bottom navbar; map switch, drag, follow and zoom')

  await page.locator('.mission-details').scrollIntoViewIfNeeded()
  const current = page.locator('.carousel-slide[data-current="true"]')
  await page.getByRole('button', { name: 'Detalle siguiente' }).click()
  await page.waitForTimeout(700)
  assert.match(await current.textContent(), /Alimentación/)
  await page.locator('.orbitium-carousel').focus()
  await page.keyboard.press('ArrowRight')
  await page.waitForTimeout(700)
  assert.match(await current.textContent(), /Enlace de radio/)
  await capture(page, 'mobile-details')
  report.checks.push('Secondary carousel: arrows and keyboard navigation')

  // Every detail card should fit its text with only its normal bottom padding.
  for (const width of [320, 393, 430, 1366]) {
    await page.setViewportSize({ width, height: 900 })
    await page.locator('.orbitium-carousel').focus()
    await page.keyboard.press('Home')
    // Use the previous arrow to reach the first card independently of Home support.
    const previous = page.getByRole('button', { name: 'Detalle anterior' })
    while (await previous.isEnabled()) {
      await previous.click()
      await page.waitForTimeout(350)
    }
    for (let index = 0; index < 5; index++) {
      await page.waitForTimeout(350)
      const geometry = await current.evaluate(slide => {
        const card = slide.querySelector('.carousel-card').getBoundingClientRect()
        const article = slide.querySelector('.mission-detail-card').getBoundingClientRect()
        return { gap: card.bottom - article.bottom, height: card.height }
      })
      assert.ok(geometry.gap >= 12 && geometry.gap <= 24, `Excess space or clipped detail ${index} at ${width}px: ${JSON.stringify(geometry)}`)
      if (index < 4) await page.getByRole('button', { name: 'Detalle siguiente' }).click()
    }
  }
  await capture(page, 'compact-device-card')
  await page.setViewportSize({ width: 393, height: 852 })
  report.checks.push('All 5 detail cards fit content with 12–24px bottom spacing at 320/393/430/1366px')

  await page.locator('#mission-archive').scrollIntoViewIfNeeded()
  await page.waitForTimeout(700)
  const filter = page.getByRole('combobox', { name: 'Ventana del archivo' })
  await filter.click()
  await page.getByRole('option', { name: '6 h', exact: true }).click()
  assert.match(await filter.textContent(), /6 h/)
  await page.waitForTimeout(700)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: /CSV completo/ }).click()
  assert.match((await download).suggestedFilename(), /simulado.*\.csv$/)
  await page.getByRole('button', { name: /Histórico/ }).click()
  await page.getByRole('dialog').waitFor()
  await page.getByRole('button', { name: 'Cerrar diálogo' }).click()
  await page.getByRole('list', { name: 'Entradas de bitácora técnica' }).scrollIntoViewIfNeeded()
  await page.getByRole('listitem').first().waitFor({ state: 'visible' })
  report.checks.push('Archive filter, CSV download, history dialog, read-only technical log')

  async function checkWorkspace(dialog, name, viewport) {
    const layout = await dialog.evaluate(element => {
      const rect = element.getBoundingClientRect()
      const heading = element.querySelector('.dialog-heading')
      const controls = [...element.querySelectorAll('button, input:not([type="checkbox"]), select, [role="combobox"]')]
        .filter(control => control.getBoundingClientRect().width > 0 && !control.closest('[inert]'))
      return {
        left: rect.left, right: rect.right, bottom: rect.bottom,
        overflow: element.scrollWidth - element.clientWidth,
        titleSize: parseFloat(getComputedStyle(heading.querySelector('h2')).fontSize),
        smallControls: controls.filter(control => control.getBoundingClientRect().height < 43).map(control => control.outerHTML.slice(0, 180)),
        smallFields: controls.filter(control => control.matches('input, select') && parseFloat(getComputedStyle(control).fontSize) < 16).length,
      }
    })
    assert.ok(layout.left >= -1 && layout.right <= viewport.width + 1 && layout.bottom <= viewport.height + 1, `${name} outside viewport: ${JSON.stringify(layout)}`)
    assert.ok(layout.overflow <= 1, `${name} horizontal overflow: ${JSON.stringify(layout)}`)
    assert.ok(layout.titleSize >= 16, `${name} title too small`)
    assert.deepEqual(layout.smallControls, [], `${name} touch controls too small`)
    assert.equal(layout.smallFields, 0, `${name} fields must be at least 16px`)
    await dialog.evaluate(element => { element.scrollTop = element.scrollHeight })
    const closeBox = await dialog.getByRole('button', { name: 'Cerrar diálogo' }).boundingBox()
    assert.ok(closeBox.y >= 0 && closeBox.y + closeBox.height <= viewport.height, `${name} close button must stay visible`)
    await dialog.evaluate(element => { element.scrollTop = 0 })
  }

  for (const viewport of [{ width: 320, height: 568 }, { width: 393, height: 852 }, { width: 430, height: 900 }, { width: 852, height: 393 }, { width: 1366, height: 900 }]) {
    await page.setViewportSize(viewport)
    await page.getByRole('button', { name: /Recuperación/ }).click()
    const recovery = page.getByRole('dialog', { name: 'Recuperación · Rastreo y predicción', exact: true })
    await recovery.locator('.leaflet-host').waitFor()
    await checkWorkspace(recovery, 'Recovery', viewport)
    await capture(page, `recovery-${viewport.width}`)
    if (viewport.width === 393) {
      await recovery.locator('.predictor-panel').scrollIntoViewIfNeeded()
      const ascent = recovery.getByRole('slider', { name: /Vel\. ascenso/ })
      const initialAscent = Number(await ascent.inputValue())
      await ascent.focus()
      await ascent.press('ArrowRight')
      assert.ok(Number(await ascent.inputValue()) > initialAscent)
      await capture(page, 'recovery-parameters-393')
    }
    await recovery.locator('.prediction-panel').scrollIntoViewIfNeeded()
    await recovery.locator('.prediction-panel').waitFor()
    const next = recovery.getByRole('button', { name: 'Detalle siguiente' })
    if (await next.count()) {
      await next.click()
      await page.waitForTimeout(700)
      assert.match(await recovery.locator('.carousel-slide[data-current="true"]').textContent(), /Referencias utilizadas/)
    }
    await recovery.getByRole('button', { name: /Planificación independiente/ }).click()
    const planning = page.getByRole('dialog', { name: 'Planificación independiente', exact: true })
    await planning.locator('.planning-map').waitFor()
    await checkWorkspace(planning, 'Planning', viewport)
    if (viewport.width === 393) await capture(page, 'planning-overview-393')
    const submit = planning.getByRole('button', { name: 'Generar predicción' })
    assert.equal(await submit.isDisabled(), true)
    await planning.getByRole('checkbox').check()
    await planning.getByRole('spinbutton', { name: 'Latitud · grados', exact: true }).fill('91')
    assert.equal(await submit.isDisabled(), true)
    await planning.getByRole('spinbutton', { name: 'Latitud · grados', exact: true }).fill('20')
    assert.equal(await submit.isEnabled(), true)
    await capture(page, `planning-${viewport.width}`)
    await page.keyboard.press('Escape')
    await planning.waitFor({ state: 'detached' })
    assert.equal(await recovery.isVisible(), true, 'Escape must only close the nested planning dialog')
    assert.equal(await recovery.getByRole('button', { name: /Planificación independiente/ }).evaluate(element => element === document.activeElement), true)
    assert.equal(await page.evaluate(() => document.body.style.overflow), 'hidden')
    await recovery.getByRole('button', { name: /Planificación independiente/ }).click()
    await planning.getByRole('checkbox').check()
    await planning.getByRole('button', { name: 'Generar predicción' }).click()
    await planning.waitFor({ state: 'detached' })
    await recovery.getByRole('button', { name: 'Cerrar diálogo' }).click()

    await page.getByRole('button', { name: /Histórico/ }).click()
    const history = page.getByRole('dialog', { name: 'Reproducción histórica', exact: true })
    await history.locator('.leaflet-host').waitFor()
    await checkWorkspace(history, 'History', viewport)
    const speed = history.getByRole('combobox', { name: 'Velocidad de reproducción' })
    await speed.click()
    await history.getByRole('option', { name: '5×', exact: true }).click()
    assert.match(await speed.textContent(), /5×/)
    await history.getByRole('button', { name: /Reproducir/ }).click()
    await history.getByRole('button', { name: /Pausar/ }).click()
    await capture(page, `history-${viewport.width}`)
    await page.keyboard.press('Escape')
    await history.waitFor({ state: 'detached' })
  }
  report.checks.push('Recovery, history and nested planning at 320/393/430/852/1366px: reflow, touch sizes, 16px fields, sticky close, Escape/focus, validation, demo prediction and replay speed/play/pause')

  for (const width of [320, 393, 430, 852, 1366]) {
    await page.setViewportSize({ width, height: width > 760 ? 900 : 852 })
    await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }))
    await page.waitForTimeout(400)
    const dimensions = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }))
    assert.equal(dimensions.width, width, `viewport expanded at ${width}`)
    assert.ok(dimensions.scroll <= width, `horizontal overflow at ${width}`)
    await capture(page, `viewport-${width}`, width === 1366)
  }
  report.checks.push('No horizontal overflow at 320, 393, 430, 852 and 1366 CSS px')

  for (const viewport of [{ width: 320, height: 568 }, { width: 852, height: 393 }]) {
    await page.setViewportSize(viewport)
    await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }))
    await menu.click()
    await page.waitForTimeout(500)
    const layout = await page.locator('.card-nav__panel').evaluate(element => ({ bottom: element.getBoundingClientRect().bottom, viewport: innerHeight }))
    assert.ok(layout.bottom <= layout.viewport, 'Open menu must fit inside a short viewport')
    await page.getByRole('link', { name: 'Bitácora técnica', exact: true }).scrollIntoViewIfNeeded()
    await page.getByRole('link', { name: 'Bitácora técnica', exact: true }).focus()
    await page.keyboard.press('Escape')
    assert.equal(await menu.evaluate(element => document.activeElement === element), true)
  }
  report.checks.push('Menu fits 320x568 and 852x393; last links remain scrollable and keyboard accessible')

  await page.setViewportSize({ width: 393, height: 852 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.locator('.mission-aurora canvas').waitFor({ state: 'detached' })
  await menu.click()
  assert.equal(await menu.getAttribute('aria-expanded'), 'true')
  await page.keyboard.press('Escape')
  await page.emulateMedia({ forcedColors: 'active' })
  await capture(page, 'forced-colors')
  report.checks.push('Reduced motion removes Aurora; menu remains operable; forced-color capture')

  const fallbackContext = await browser.newContext({ viewport: { width: 393, height: 852 }, hasTouch: true, isMobile: true })
  await fallbackContext.route('**/*', route => {
    const url = new URL(route.request().url())
    return url.hostname === '127.0.0.1' && !url.pathname.startsWith('/api') ? route.continue() : route.abort()
  })
  await fallbackContext.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      if (type === 'webgl2' || type === 'webgl') return null
      return original.call(this, type, ...args)
    }
  })
  const fallback = await fallbackContext.newPage()
  fallback.on('pageerror', error => errors.push(error.message))
  await fallback.goto('http://127.0.0.1:5188', { waitUntil: 'networkidle' })
  await fallback.locator('.mission-summary').waitFor()
  assert.equal(await fallback.locator('.mission-bottom-nav').count(), 0)
  await fallback.locator('#mission-map').scrollIntoViewIfNeeded()
  await fallback.waitForTimeout(800)
  assert.equal(await fallback.locator('#mission-map').isVisible(), true)
  await capture(fallback, 'webgl-fallback')
  await fallbackContext.close()
  report.checks.push('WebGL unavailable: static header and accessible map without main navbar')

  await page.emulateMedia({ forcedColors: 'none' })
  await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }))
  await menu.click()
  await page.getByRole('combobox', { name: 'Fuente de datos' }).selectOption('live')
  await page.getByText('La estación aún no está disponible', { exact: true }).waitFor()
  assert.equal(await page.locator('.mission-summary').count(), 0)
  report.checks.push('Unavailable real station never falls back to simulated telemetry')
  assert.deepEqual(errors, [])
  console.log(JSON.stringify(report, null, 2))
  await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2) + '\n')
  console.log(`UI checks passed. Evidence: ${output}`)
} finally {
  await browser?.close()
  await server.close()
}
