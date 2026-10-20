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
  const context = await browser.newContext({ viewport: { width: 393, height: 852 }, isMobile: true, hasTouch: true })
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
  assert.equal(await page.getByRole('navigation', { name: 'Secciones de misión' }).getByRole('link').count(), 4)
  assert.equal(await page.locator('.mission-summary').getByRole('meter').count(), 1)
  assert.equal(await page.locator('.mission-summary').getByRole('slider').count(), 0)
  assert.equal(await page.locator('.mission-aurora canvas').evaluate(canvas => canvas.getContext('webgl2')?.isContextLost()), false)
  report.frames.header = await frames(page)
  await capture(page, 'mobile-393')
  assert.equal(await page.getByRole('combobox', { name: 'Fuente de datos' }).count(), 0)
  assert.equal(await page.locator('.card-nav__content').getAttribute('inert'), '')

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

  await page.getByRole('link', { name: 'Mapa', exact: true }).click()
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
  report.checks.push('Gooey navigation, map switch, drag, follow and zoom')

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

  await page.getByRole('link', { name: 'Archivo', exact: true }).click()
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
  assert.equal(await fallback.locator('.gooey-nav__fallback').evaluate(element => getComputedStyle(element).display), 'block')
  await fallback.getByRole('link', { name: 'Mapa', exact: true }).click()
  await fallback.waitForTimeout(800)
  assert.equal(await fallback.getByRole('link', { name: 'Mapa', exact: true }).getAttribute('aria-current'), 'page')
  await capture(fallback, 'webgl-fallback')
  await fallbackContext.close()
  report.checks.push('WebGL unavailable: static header and functional Gooey fallback navigation')

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
