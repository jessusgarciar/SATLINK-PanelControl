import assert from 'node:assert/strict'
import { parseSnapshot, parseMessage, parseTelemetry } from '../src/infrastructure/http/validation.ts'

let input = ''
for await (const chunk of process.stdin) input += chunk
const data = JSON.parse(input)
const snapshot = parseSnapshot(data.snapshot, 'test-flight')
assert.equal(snapshot.permissions.canCommand, false)
assert.equal(snapshot.permissions.canPredict, false)
assert.equal(snapshot.telemetry[0].id, parseMessage(data.stream).data.id)
for (const sample of data.history.items) assert.equal(parseTelemetry(sample).missionId, 'test-flight')
assert.equal(data.history.nextCursor, null)
