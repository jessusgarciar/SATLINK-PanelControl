import test from 'node:test'
import assert from 'node:assert/strict'
import { latestReadings } from '../src/presentation/readings.ts'
import { latestPosition, targetAltitude } from '../src/domain/mission.ts'
import { parsePackets, parseTelemetry } from '../src/infrastructure/http/validation.ts'

const empty = { missionId: 'flight', id: 'one', receivedAt:'2026-10-23T12:00:00Z', frameCounter:1,
 latitude:null,longitude:null,altitudeGpsM:null,relativeAltitudeM:null,altitudeBarometricM:null,
 temperatureC:null,humidityPct:null,pressureHpa:null,batteryV:null,rssiDbm:null,snrDb:null,
 verticalSpeedMs:null,device:null,radio:null }
const gps = { ...empty, id:'gps',latitude:21,longitude:-102,altitudeGpsM:15000,
 packet:{presentFields:['latitude','longitude','altitudeGpsM'],presentDeviceFields:['gpsFix']},device:{gpsFix:true} }
const air = { ...empty, id:'air',receivedAt:'2026-10-23T12:00:03Z',temperatureC:0,
 packet:{presentFields:['temperatureC','humidityPct'],presentDeviceFields:['batteryPct']},device:{batteryPct:null} }

test('radiosonda partial packets retain unrelated values and clear explicit unavailable measurements',()=>{
 const old = {...empty,id:'old',temperatureC:25,humidityPct:70,device:{batteryPct:80}}
 const latest=latestReadings([old,gps,air],'flight')
 assert.equal(latest.values.temperatureC,0)
 assert.equal(latest.values.humidityPct,null)
 assert.equal(latest.values.device.batteryPct,null)
 assert.equal(latest.values.altitudeGpsM,15000)
 assert.equal(latest.observedAt.altitudeGpsM,gps.receivedAt)
 assert.equal(latestPosition([gps,air]).id,'gps')
 const nofix={...gps,id:'nofix',receivedAt:'2026-10-23T12:10:00Z',latitude:null,longitude:null,altitudeGpsM:null}
 assert.equal(latestReadings([gps,air,nofix],'flight').values.altitudeGpsM,null)
 assert.equal(latestPosition([gps,air,nofix]).id,'nofix')
})
test('absolute mission target does not add launch altitude',()=>{
 const mission={altitudeTargetMode:'absolute',launch:{altitudeM:1870},targetRelativeAltitudeM:15000}
 assert.equal(targetAltitude(mission),15000)
 assert.equal(targetAltitude({...mission,altitudeTargetMode:'relative'}),16870)
})
test('packet history preserves raw event and rejected reason without merging other packages',()=>{
 const first={id:'1',receivedAt:null,ingestedAt:'2026-10-23T12:00:00Z',status:'rejected',reason:'bad length',decoded:{},raw:{fPort:21,data:'YmFk'},rawBase64:''}
 const page=parsePackets({items:[first],nextCursor:null})
 assert.deepEqual(page.items[0],{...first,ingestedAt:new Date(first.ingestedAt).toISOString()})
 assert.throws(()=>parsePackets({items:[{...first,status:'unknown'}],nextCursor:null}))
})
test('telemetry parser preserves packet presence and does not infer a fix',()=>{
 const sample=parseTelemetry(gps)
 assert.deepEqual(sample.packet.presentFields,gps.packet.presentFields)
 assert.equal(sample.altitudeGpsM,15000)
 assert.equal(parseTelemetry({...empty,packet:null}).packet,undefined)
})
