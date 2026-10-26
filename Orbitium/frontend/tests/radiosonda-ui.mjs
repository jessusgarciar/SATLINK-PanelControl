// Fixtures only: broker, hardware and external providers are blocked.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { chromium } from 'playwright'
import { DemoMissionGateway } from '../src/infrastructure/demo/DemoMissionGateway.ts'

process.env.VITE_DATA_SOURCE='live'
process.env.VITE_MISSION_ID='synthetic-radio-ui'
process.env.VITE_DEMO_PREDICTION='local'
const root=fileURLToPath(new URL('../',import.meta.url))
const output=fileURLToPath(new URL('../../.local/ui-evidence/',import.meta.url))
await mkdir(output,{recursive:true})
const server=await createServer({root,server:{host:'127.0.0.1',port:5192,strictPort:true,open:false}})
const fixture=await new DemoMissionGateway().load(new AbortController().signal)
fixture.mission={...fixture.mission,id:'synthetic-radio-ui',name:'Heltec SINTÉTICA',telemetryProtocol:'radiosonda-v1',altitudeTargetMode:'absolute',phase:'unknown',startedAt:null,staleAfterSeconds:900,flightState:{phase:'EN VUELO',enVuelo:true,watchdogActive:true,observedAt:new Date().toISOString()}}
fixture.telemetry=fixture.telemetry.slice(-4).map(s=>({...s,missionId:fixture.mission.id,packet:{fPort:20,packetType:'posicion',presentFields:['latitude','longitude','altitudeGpsM','relativeAltitudeM'],presentDeviceFields:['gpsFix']}}))
fixture.prediction=null
fixture.commands=[]
fixture.permissions={canCommand:true,canPredict:false}
fixture.csrfToken='synthetic-csrf'
fixture.commandSettings={enabled:true,supportedTypes:['PING','RELEASE_NOW'],reason:null,uplinkIntervalSeconds:600}
const packet=(id,port,decoded)=>({id,receivedAt:new Date().toISOString(),ingestedAt:new Date().toISOString(),status:'accepted',reason:null,decoded:{fPort:port,...decoded},raw:{fPort:port,fCnt:Number(id),data:'AAA='},rawBase64:''})
const packets=[packet('2',21,{packetType:'atmosfera',temperatureC:31.86,pressureHpa:812.6,humidityPct:null,batteryPct:null}),packet('1',20,{packetType:'posicion',latitude:21,longitude:-102,altitudeGpsM:15000})]
let browser
try {
 await server.listen()
 browser=await chromium.launch({channel:process.platform==='win32'?'msedge':'chromium',headless:true})
 const context=await browser.newContext({viewport:{width:375,height:812},reducedMotion:'reduce'})
 const posts=[]
 await context.routeWebSocket(/\/api\//,()=>{})
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url())
  if(url.hostname!=='127.0.0.1') return route.abort()
  if(!url.pathname.startsWith('/api/')) return route.continue()
  if(url.pathname.endsWith('/dashboard')) return route.fulfill({json:fixture})
  if(url.pathname.endsWith('/packets')) return route.fulfill({json:{items:url.searchParams.has('cursor')?[{...packet('0',21,{}),status:'rejected',reason:'Radiosonda: longitud inválida'}]:packets,nextCursor:url.searchParams.has('cursor')?null:'older'}})
  if(url.pathname.endsWith('/commands')) {
   const body=req.postDataJSON(); posts.push(body)
   const command={...body,id:crypto.randomUUID(),missionId:fixture.mission.id,seq:posts.length,status:'pending',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),evidence:'Solicitud SINTÉTICA',simulated:false,watchdogSeconds:3300}
   return route.fulfill({status:202,json:command})
  }
  return route.fulfill({status:404,json:{detail:'Fixture only'}})
 })
 const page=await context.newPage(),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.goto('http://127.0.0.1:5192',{waitUntil:'networkidle'})
 await page.getByRole('button',{name:'MARCO',exact:true}).waitFor()
 assert.equal(await page.getByRole('button',{name:'Iniciar misión',exact:true}).count(),0)
 assert.equal(await page.getByText('Altitud del dispositivo',{exact:true}).count(),1)
 assert.equal(await page.getByRole('button',{name:'CORTE',exact:true}).isEnabled(),true)
 for(const viewport of [{width:375,height:812},{width:1280,height:900},{width:852,height:393}]) {
  await page.setViewportSize(viewport)
  await page.getByRole('button',{name:'Información de misión',exact:true}).click()
  const dialog=page.getByRole('dialog',{name:'Información de misión',exact:true})
  await dialog.getByRole('heading',{name:'Historial de paquetes',exact:true}).waitFor()
  await page.locator('.packet-select').first().waitFor()
  assert.equal(await page.locator('.packet-select').count(),2)
  await page.locator('.packet-select').last().click()
  await page.locator('.packet-detail').getByText('15000',{exact:true}).waitFor()
  await page.locator('.packet-select').first().click()
  await page.locator('.packet-detail').getByText('31.86',{exact:true}).waitFor()
  assert.equal(await page.locator('.packet-detail').getByText('15000',{exact:true}).count(),0)
  await page.getByRole('button',{name:'Cargar paquetes anteriores',exact:true}).click()
  await page.locator('.packet-select').filter({hasText:'Rechazado'}).click()
  await page.locator('.packet-detail').getByText('Radiosonda: longitud inválida',{exact:true}).waitFor()
  assert.equal(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true)
  await page.getByRole('heading',{name:'Historial de paquetes'}).scrollIntoViewIfNeeded()
  await page.screenshot({path:`${output}/radiosonda-packets-${viewport.width}.png`})
  if(viewport.width===375) {
   await page.locator('.packet-select').filter({hasText:'atmosfera'}).click()
   await page.locator('.packet-detail').scrollIntoViewIfNeeded()
   await page.screenshot({path:`${output}/radiosonda-packet-detail-375.png`})
  }
  await page.keyboard.press('Escape')
  assert.equal(await page.getByRole('button',{name:'Información de misión',exact:true}).evaluate(el=>el===document.activeElement),true)
 }
 await page.getByRole('button',{name:'MARCO',exact:true}).click()
 await page.getByText('Solicitud SINTÉTICA',{exact:true}).waitFor()
 assert.equal(posts[0].type,'PING')
 await page.getByRole('button',{name:'CORTE',exact:true}).click()
 const confirm=page.getByRole('dialog',{name:'Confirmar corte de vuelo'})
 const send=confirm.getByRole('button',{name:'Solicitar liberación',exact:true})
 assert.equal(await send.isDisabled(),true)
 await confirm.getByRole('textbox').fill('LIBERAR')
 assert.equal(await send.isEnabled(),true)
 await send.click()
 assert.equal(posts[1].type,'RELEASE_NOW')
 assert.deepEqual(errors,[])
 console.log(JSON.stringify({passed:true,checks:['mobile desktop landscape','packet selection','pagination and rejected packets','no horizontal overflow','keyboard focus restoration','autonomous start','Marco request','cut double confirmation'],hardware:false}))
} finally {await browser?.close();await server.close()}
