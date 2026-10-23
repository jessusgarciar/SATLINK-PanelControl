import test from 'node:test'
import assert from 'node:assert/strict'
import { HttpMissionGateway } from '../src/infrastructure/http/HttpMissionGateway.ts'
import { subscribeMission } from '../src/infrastructure/websocket/missionStream.ts'

test('HTTP POST carries session, CSRF and idempotency; no automatic retry', async (t) => {
  const original = globalThis.fetch
  t.after(() => {
    globalThis.fetch = original
  })
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return new Response(
      JSON.stringify({
        id: 'cmd-1',
        missionId: 'test',
        clientRequestId: 'r-1',
        type: 'PING',
        status: 'pending',
        createdAt: '2026-10-01T00:00:00Z',
        updatedAt: '2026-10-01T00:00:00Z',
        evidence: 'Registrado',
        simulated: false,
      }),
      { headers: { 'Content-Type': 'application/json' } },
    )
  }
  const gateway = new HttpMissionGateway('/api/v1', 'test')
  const command = await gateway.sendCommand('PING', 'r-1', 'csrf-1')
  assert.equal(command.status, 'pending')
  assert.equal(calls[0].url, '/api/v1/missions/test/commands')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.headers['Idempotency-Key'], 'r-1')
  assert.equal(calls[0].options.headers['X-CSRF-Token'], 'csrf-1')
  globalThis.fetch = async () => {
    calls.push({})
    throw new TypeError('Network failure')
  }
  await assert.rejects(gateway.sendCommand('PING', 'r-2', 'csrf-1'), /conectar/)
  assert.equal(calls.length, 2)
})
test('HTTP rejects HTML responses and unauthorized commands', async (t) => {
  const original = globalThis.fetch
  t.after(() => {
    globalThis.fetch = original
  })
  const gateway = new HttpMissionGateway('/api/v1', 'test')
  globalThis.fetch = async () =>
    new Response('<html/>', { headers: { 'Content-Type': 'text/html' } })
  await assert.rejects(gateway.load(new AbortController().signal), /no devolvió JSON/)
  globalThis.fetch = async () => new Response(null, { status: 403 })
  await assert.rejects(gateway.sendCommand('PING', 'r', 'csrf'), /permiso/)
})
test('saving parameters shows the conflict detail and distinguishes unsupported methods', async (t) => {
  const original = globalThis.fetch
  t.after(() => { globalThis.fetch = original })
  const gateway = new HttpMissionGateway('/api/v1', 'orbitium')
  let calls = 0
  const respond = (status, detail) => {
    globalThis.fetch = async (url, options) => {
      calls++
      assert.equal(url, '/api/v1/missions/orbitium/parameters')
      assert.equal(options.method, 'PUT')
      assert.equal(options.headers['X-CSRF-Token'], 'csrf')
      return new Response(JSON.stringify({ detail }), {
        status, headers: { 'Content-Type': 'application/json' },
      })
    }
  }
  respond(409, 'El archivo local no corresponde a la misión activa')
  await assert.rejects(gateway.saveParameters({}, 'csrf'), {
    message: 'El archivo local no corresponde a la misión activa',
  })
  for (const detail of [null, {}, '   ']) {
    respond(409, detail)
    await assert.rejects(gateway.saveParameters({}, 'csrf'), /solicitud incompatible/)
  }
  respond(405, 'Method Not Allowed')
  await assert.rejects(gateway.saveParameters({}, 'csrf'), /servidor no admite esta operación/)
  assert.equal(calls, 5, 'Failed saves are never retried automatically')
})

test('WebSocket reconnects, ignores malformed messages and fully cleans up', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const original = globalThis.WebSocket
  const sockets = []
  class FakeSocket {
    constructor() {
      sockets.push(this)
    }
    close(code = 1000) {
      this.closed = true
      this.onclose?.({ code })
    }
  }
  globalThis.WebSocket = FakeSocket
  t.after(() => {
    globalThis.WebSocket = original
    t.mock.timers.reset()
  })
  const statuses = [],
    errors = [],
    messages = []
  const stop = subscribeMission(
    'ws://localhost/test',
    (m) => messages.push(m),
    (s) => statuses.push(s),
    (e) => errors.push(e),
  )
  sockets[0].onopen()
  sockets[0].onmessage({ data: '{broken' })
  sockets[0].onmessage({ data: '{"type":"heartbeat"}' })
  assert.equal(errors.length, 1)
  assert.equal(messages.length, 0)
  sockets[0].close(1006)
  assert.equal(statuses.at(-1), 'reconnecting')
  t.mock.timers.tick(1500)
  assert.equal(sockets.length, 2)
  stop()
  t.mock.timers.tick(120000)
  assert.equal(sockets.length, 2)
  assert.equal(sockets[1].closed, true)
})
test('policy-close stops reconnecting instead of looping after session expiry', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const original = globalThis.WebSocket
  let socket
  let count = 0
  globalThis.WebSocket = class {
    constructor() {
      socket = this
      count++
    }
    close() {}
  }
  t.after(() => {
    globalThis.WebSocket = original
    t.mock.timers.reset()
  })
  const errors = []
  const stop = subscribeMission(
    'ws://localhost/test',
    () => {},
    () => {},
    (error) => errors.push(error),
  )
  socket.onclose({ code: 4401 })
  t.mock.timers.tick(120000)
  assert.equal(count, 1)
  assert.match(errors[0], /Sesión expirada/)
  stop()
})
