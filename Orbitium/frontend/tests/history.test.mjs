import test from 'node:test'
import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'
import { HttpMissionGateway } from '../src/infrastructure/http/HttpMissionGateway.ts'
import { MissionController } from '../src/application/MissionController.ts'
import { ReplayController } from '../src/application/ReplayController.ts'
import { WindowController } from '../src/application/WindowController.ts'
import { decimate, demoCsv, demoWindow, timeRange } from '../src/domain/history.ts'
import { parseIngestion, parseMessage, parseTelemetry, parseWindow, parseHistory } from '../src/infrastructure/http/validation.ts'

const fixture = await new DemoMissionGateway().load(new AbortController().signal)
const start = Date.parse('2026-10-02T12:00:00Z')
const sample = fixture.telemetry[0]
const samples = Array.from({length: 1400}, (_, i) => ({ ...sample, id: 'row-' + i, receivedAt: new Date(start + i * 1000).toISOString(), frameCounter: i }))
const range = { from: samples[0].receivedAt, to: new Date(start + 1400 * 1000).toISOString() }
const settle = async () => { await setImmediate(); await setImmediate() }

test('device flags, radio DR zero, and legacy missing metadata remain distinct', () => {
  const data = parseTelemetry({ ...sample, device: { gpsActive: false, gpsFix: false, charging: null, usbPowered: true, satellites: 0, batteryPct: 255 }, radio: { gatewayId: 'test', dataRate: 0, fPort: 10, frequencyHz: -1 } })
  assert.equal(data.device.gpsFix, false)
  assert.equal(data.device.satellites, 0)
  assert.equal(data.device.batteryPct, null)
  assert.equal(data.radio.dataRate, 0)
  assert.equal(data.radio.frequencyHz, null)
  assert.equal(parseTelemetry({ ...sample, device: undefined, radio: undefined }).device, null)
})

test('ingestion messages describe MQTT independently of sensor freshness', () => {
  const ingestion = { source: 'test', status: 'disabled', updatedAt: new Date(start).toISOString() }
  assert.deepEqual(parseMessage({ type: 'ingestion', data: ingestion }), { type: 'ingestion', data: ingestion })
  assert.equal(parseIngestion(undefined), null)
  assert.throws(() => parseIngestion({ ...ingestion, status: 'active' }), /desconocido/)
})

test('window includes its start, excludes its end and keeps visual endpoints', () => {
  const data = demoWindow(samples, { from: samples[1].receivedAt, to: samples[1399].receivedAt })
  assert.equal(data.total, 1398)
  assert.equal(data.series.length, 600)
  assert.equal(data.track.length, 500)
  assert.equal(data.series[0].id, 'row-1')
  assert.equal(data.series.at(-1).id, 'row-1398')
  assert.equal(decimate(samples, 500).at(-1).id, 'row-1399')
  assert.equal(timeRange('all', start).from, null)
  assert.equal(Date.parse(timeRange('1h', start).from), start - 3600000)
})

test('history and window parsers reject cross-mission payloads and oversized previews', () => {
  assert.throws(() => parseHistory({items: samples.slice(0,1), nextCursor:null}, 'other'), /otra misión/)
  assert.throws(() => parseWindow({...range,total:1400,series:samples.slice(0,601),track:[]}, sample.missionId), /lista/)
  const parsed = parseWindow(demoWindow(samples, range), sample.missionId)
  assert.equal(parsed.total, 1400)
})

test('changing archive filters aborts requests, ignores stale results and retains valid data on errors', async () => {
  const requests = []
  const controller = new WindowController({ window: (range, signal) => new Promise((resolve, reject) => requests.push({range,signal,resolve,reject})) })
  void controller.load(range)
  void controller.load({ ...range, from: null })
  assert.equal(requests[0].signal.aborted, true)
  const current = demoWindow(samples, range)
  requests[1].resolve(current); await settle()
  requests[0].resolve({...current,total:1}); await settle()
  assert.equal(controller.getSnapshot().data.total,1400)
  void controller.load(range)
  requests[2].reject(new Error('Offline')); await settle()
  assert.equal(controller.getSnapshot().data.total,1400)
  assert.equal(controller.getSnapshot().error,'Offline')
  controller.dispose()
})

test('replay uses original time, speed and paging with bounded memory, then can restart', async () => {
  const calls = []
  const gateway = { history: async (interval, cursor) => {
    calls.push({...interval,cursor})
    const offset = Number(cursor ?? 0)
    return {items: samples.slice(offset, offset + 200), nextCursor: offset + 200 < samples.length ? String(offset + 200) : null}
  } }
  const replay = new ReplayController(gateway, range)
  await replay.reset()
  assert.equal(replay.getSnapshot().samples[0].receivedAt, range.from)
  replay.setSpeed(10); replay.play()
  await replay.advance(100)
  assert.equal(replay.getSnapshot().samples.at(-1).id, 'row-1')
  replay.pause(); await replay.advance(100000)
  assert.equal(replay.getSnapshot().samples.at(-1).id, 'row-1')
  replay.play()
  for (let i=0;i<10 && !replay.getSnapshot().ended;i++) await replay.advance(200000)
  assert.equal(replay.getSnapshot().ended,true)
  assert.equal(replay.getSnapshot().samples.length,1200)
  assert.equal(replay.getSnapshot().samples.at(-1).id,'row-1399')
  assert.equal(replay.getSnapshot().virtualNow,Date.parse(samples.at(-1).receivedAt))
  assert.equal(calls.length,7)
  assert.ok(calls.every((call) => call.to === range.to && call.from === range.from))
  await replay.reset()
  assert.equal(replay.getSnapshot().samples.length,1)
  assert.equal(replay.getSnapshot().playing,false)
  replay.dispose()
})

test('replay disposal cancels page loading and prevents obsolete readings', async () => {
  let complete, signal
  const replay = new ReplayController({history: (_, __, inputSignal) => {signal=inputSignal; return new Promise((resolve) => {complete=resolve})}}, range)
  const load = replay.reset()
  replay.dispose()
  assert.equal(signal.aborted,true)
  complete({items:samples.slice(0,200),nextCursor:'200'})
  await load
  assert.equal(replay.getSnapshot().samples.length,0)
})

test('demo CSV exports every row and all derived fields without inventing raw uplinks', () => {
  const csv = demoCsv(samples)
  const rows = csv.trim().split('\r\n')
  assert.equal(rows.length,1401)
  assert.ok(rows[0].includes('altitudeBarometricM'))
  assert.ok(rows[0].includes('verticalSpeedMs'))
  assert.ok(rows[0].includes('device_gpsFix'))
  assert.ok(rows[1].includes('"demo"'))
  assert.ok(rows[1].endsWith(',""'))
})

test('HTTP archive sends identical filters to window, replay and CSV and validates response types', async (t) => {
  const original=globalThis.fetch
  t.after(() => {globalThis.fetch=original})
  const calls=[]
  globalThis.fetch=async (url,options) => {
    calls.push({url,options})
    if(url.includes('export.csv')) return new Response(demoCsv(samples.slice(0,2)),{headers:{'Content-Type':'text/csv;charset=utf-8'}})
    if(url.includes('/window')) return Response.json(demoWindow(samples,range))
    return Response.json({items:samples.slice(0,200),nextCursor:'next'})
  }
  const gateway = new HttpMissionGateway('/api/v1',sample.missionId)
  const signal = new AbortController().signal
  await gateway.window(range,signal)
  await gateway.history(range,'previous',signal)
  assert.ok((await gateway.exportCsv(range,signal)).size>0)
  for(const {url,options} of calls){const params=new URL(url,'http://localhost').searchParams; assert.equal(params.get('from'),range.from); assert.equal(params.get('to'),range.to); assert.equal(options.credentials,'include')}
  assert.equal(new URL(calls[1].url,'http://localhost').searchParams.get('cursor'),'previous')
  globalThis.fetch=async () => new Response('<html/>',{headers:{'Content-Type':'text/html'}})
  await assert.rejects(gateway.exportCsv(range,signal),/CSV/)
})

test('late MQTT snapshots cannot overwrite a newer state; technical log stays bounded', async () => {
  let emit
  const ingestion={source:'test',status:'connecting',updatedAt:new Date(start).toISOString()}
  const gateway={mode:'live',load:async () => ({...fixture,ingestion}),subscribe:(message,status)=>{emit=message; status('connected');return()=>{}}}
  const controller=new MissionController(gateway)
  const stop=controller.start();await settle()
  emit({type:'ingestion',data:{...ingestion,status:'reconnecting',updatedAt:new Date(start+1000).toISOString()}})
  await controller.refresh()
  assert.equal(controller.getSnapshot().snapshot.ingestion.status,'reconnecting')
  assert.equal(controller.getSnapshot().connection,'connected')
  for(let i=0;i<150;i++)controller.recordTechnical('Synthetic '+i)
  assert.equal(controller.getSnapshot().technicalLog.length,100)
  assert.equal(controller.getSnapshot().snapshot.events.length,fixture.events.length)
  stop()
})

test('changing live and demo controllers disposes subscriptions and rejects late old messages', async () => {
  let emit,closed=0
  const live=new MissionController({mode:'live',load:async()=>({...fixture,telemetry:[],ingestion:null,permissions:{canCommand:false,canPredict:false}}),subscribe:(message,status)=>{emit=message;status('connected');return()=>{closed++}}})
  const stop=live.start();await settle();stop()
  emit({type:'telemetry',data:sample})
  assert.equal(live.getSnapshot().snapshot.telemetry.length,0)
  const demo=new MissionController(new DemoMissionGateway())
  const stopDemo=demo.start();await settle()
  assert.equal(demo.getSnapshot().snapshot.mission.id,'satlink-demo')
  assert.equal(demo.getSnapshot().snapshot.ingestion,null)
  assert.equal(closed,1)
  stopDemo()
})
