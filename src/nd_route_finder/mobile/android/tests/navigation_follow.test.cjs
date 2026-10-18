'use strict';

const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.resolve(__dirname, '../app/src/main/assets/route_finder.html'), 'utf8');
const script = html.slice(html.lastIndexOf('<script>') + '<script>'.length, html.lastIndexOf('</script>'));

function harness() {
  const elements = new Map();
  const toggled = {wake: []};
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      classList: {toggle() {}, add() {}, remove() {}},
      clientHeight: 720, textContent: '', value: '',
    });
    return elements.get(id);
  }
  const document = {
    getElementById: element,
    addEventListener() {},
    documentElement: {classList: {toggle() {}}},
    body: {classList: {toggle() {}}},
  };
  const phoneMap = {
    zoom: 17, pan: null,
    getZoom() {return this.zoom;},
    getSize() {return {y: 720};},
    panTo(p) {this.pan = p;},
    invalidateSize() {},
  };
  const threeD = {
    zoom: 16, camera: null,
    getZoom() {return this.zoom;},
    getCanvas() {return {clientHeight: 720};},
    easeTo(p) {this.camera = p;},
  };
  const Android = {setNavigationScreenAwake(value) {toggled.wake.push(value);}};
  const context = vm.createContext({
    document, Android, testMap: phoneMap, test3D: threeD,
    window: {addEventListener() {}},
    console, setTimeout(callback) {callback();}, clearTimeout() {},
  });
  vm.runInContext(script, context);
  vm.runInContext('map = testMap;', context);
  return {context, phoneMap, threeD, toggled};
}

test('only full-map navigation holds the Android screen awake', () => {
  const {context, toggled} = harness();
  vm.runInContext("showTab('nav'); toggleFullMap(); toggleFullMap(); showTab('plan'); toggleFullMap();", context);
  assert.deepEqual(toggled.wake, [false, true, false, false, false]);
  const native = fs.readFileSync(path.resolve(__dirname, '../app/src/main/java/com/ndroutefinder/mobile/MainActivity.java'), 'utf8');
  assert.match(native, /setNavigationScreenAwake\(boolean awake\)/);
  assert.match(native, /clearFlags\(WindowManager\.LayoutParams\.FLAG_KEEP_SCREEN_ON\)/);
});

test('2D follow preserves user zoom and looks farther ahead at wider zoom', () => {
  const {context, phoneMap} = harness();
  vm.runInContext('currentPosition = {lat:47,lon:15,heading:0,speed:5};', context);
  phoneMap.zoom = 13;
  vm.runInContext('updateFollowCamera();', context);
  const wide = phoneMap.pan[0] - 47;
  phoneMap.zoom = 18.5;
  vm.runInContext('updateFollowCamera();', context);
  const close = phoneMap.pan[0] - 47;
  assert.ok(wide > close * 20, 'look-ahead should scale with zoom');
  assert.ok(close > 0, 'position should sit behind center in direction of travel');
  assert.equal(phoneMap.zoom, 18.5, 'GPS updates must not override user zoom');
});

test('3D follow preserves zoom and pitch while rotating toward heading', () => {
  const {context, threeD} = harness();
  threeD.zoom = 13.7;
  vm.runInContext('map3d = test3D; map3dReady = true; use3D = true; currentPosition = {lat:47,lon:15,heading:95,speed:3}; updateFollowCamera();', context);
  assert.equal(threeD.camera.bearing, 95);
  assert.equal(threeD.camera.zoom, undefined);
  assert.equal(threeD.camera.pitch, undefined);
  assert.equal(threeD.zoom, 13.7);
  assert.ok(threeD.camera.center[0] > 15, 'camera should look east, ahead of rider');
});

test('near route while stopped uses forward GPX direction', () => {
  const {context} = harness();
  const result = vm.runInContext("currentPosition={lat:47.0001,lon:15,heading:270,speed:0};loadedGpx={points:[[47,15],[47.01,15]]}; navigationHeading();", context);
  assert.ok(result < 3 || result > 357, 'GPX northward segment should guide map instead of noisy compass');
});

test('full-map navigation restores GPS follow after a manual pan', () => {
  const {context} = harness();
  const enabled = vm.runInContext("setFollow(false);toggleFullMap();followPosition;", context);
  assert.equal(enabled, true);
});

test('loading a Fehring GPX removes old Graz detours and fits only that GPX', () => {
  const {context,phoneMap} = harness();
  phoneMap.fitBounds = function(bounds) { this.bounds = bounds; };
  vm.runInContext(`
    renderBaseRoute=()=>{};
    renderProfiles=()=>{};
    setRouteStats=()=>{};
    updateReverseState=()=>{};
    persistNavigationState=()=>{};
    navPoints=[{lat:47.07,lon:15.44,label:'Old Graz stop'}];
    navRoute={points:[[47.07,15.44],[46.936,16.010]]};
    currentPosition={lat:47.07,lon:15.44,heading:0,speed:0};
    lastAutoRoutePos={lat:47.07,lon:15.44};
    navBusy=true;
    window.ndLoadedGpx({
      points:[[46.9361885,16.0103516],[46.94,16.02],[46.9361885,16.0103516]],
      distanceKm:30.8
    });
  `,context);
  const result=vm.runInContext('({points:navPoints.length, hasDetour:!!navRoute, busy:navBusy, lastPos:lastAutoRoutePos, requestId:navigationRequestId})',context);
  assert.equal(result.points,0);
  assert.equal(result.hasDetour,false);
  assert.equal(result.busy,false);
  assert.equal(result.lastPos,null);
  assert.ok(result.requestId>0);
  assert.equal(phoneMap.bounds.length,3);
  assert.ok(phoneMap.bounds.every(([lat,lon])=>lat<47&&lon>15.9),'must not fit the unrelated Graz pin or GPS location');
});

test('a delayed old routing result cannot redraw the cleared Graz detour', () => {
  const {context,phoneMap} = harness();
  phoneMap.fitBounds = function(bounds) {this.bounds=bounds;};
  vm.runInContext(`
    renderBaseRoute=()=>{};renderProfiles=()=>{};setRouteStats=()=>{};updateReverseState=()=>{};persistNavigationState=()=>{};
    navPoints=[{lat:47.08,lon:15.45}]; navigationRequestId=5;
    window.ndLoadedGpx({points:[[46.936,16.010],[46.937,16.012]]});
    navPoints=[{lat:46.939,lon:16.016}];
    window.ndNavigationRouteReady({clientRequestId:5,points:[[47.07,15.44],[46.936,16.01]]});
  `,context);
  assert.equal(vm.runInContext('navRoute',context),null);
  assert.equal(vm.runInContext('navigationRequestId',context),6);
});

test('navigation tab hides the unrelated default planner start pin', () => {
  const {context,phoneMap} = harness();
  let pinRemoved = false;
  phoneMap.hasLayer = () => true;
  phoneMap.removeLayer = () => {pinRemoved=true;};
  vm.runInContext("startMarker={addTo(){}};showTab('nav');",context);
  assert.equal(pinRemoved,true);
});

test('Garmin direction arrow applies a persistent signed calibration offset', () => {
  const {context} = harness();
  const degree = vm.runInContext("document.getElementById('headingOffset').value='-35';gpsHeadingFor({source:'garmin',rawHeading:100});", context);
  assert.equal(degree, 65);
  const wrap = vm.runInContext("document.getElementById('headingOffset').value='40';gpsHeadingFor({source:'garmin',rawHeading:340});", context);
  assert.equal(wrap, 20);
});

test('phone arrow retains movement heading instead of idle handset heading', () => {
  const {context} = harness();
  const initial = vm.runInContext("gpsHeadingFor({source:'phone',lat:47,lon:15,rawHeading:180,speed:0,accuracy:5});",context);
  assert.ok(Number.isNaN(initial));
  const east = vm.runInContext("gpsHeadingFor({source:'phone',lat:47,lon:15.0002,rawHeading:180,speed:0,accuracy:5});",context);
  assert.ok(east>85 && east<95);
  const stopped = vm.runInContext("gpsHeadingFor({source:'phone',lat:47,lon:15.0002,rawHeading:240,speed:0,accuracy:5});",context);
  assert.equal(stopped,east);
  const compassDrift = vm.runInContext("gpsHeadingFor({source:'phone',lat:47,lon:15.0002,rawHeading:300,speed:4,accuracy:5});",context);
  assert.equal(compassDrift,east, 'GPS travel course must outrank the handset compass');
});

test('3D GPS arrow is an elongated shaded triangle, not the old flat glyph', () => {
  const {context} = harness();
  const svg = vm.runInContext('gpsArrow3DSvg()', context);
  assert.match(svg, /viewBox="0 0 36 48"/);
  assert.match(svg, /fill="#fb5b58"/);
  assert.match(svg, /fill="#bd1a23"/);
  assert.match(svg, /M18 3 L31 42/);
  assert.ok(!svg.includes('▲'));
});

test('3D GPS keeps Garmin calibrated bearing and shows red position if bearing missing', () => {
  const {context} = harness();
  const gps = vm.runInContext(`(function(){
    const captured={};
    map3dReady=true;
    ensure3DOverlayLayers=()=>{};
    map3d={getSource(id){return {setData(v){captured[id]=v;}};}};
    document.getElementById('headingOffset').value='-30';
    const compass=gpsHeadingFor({source:'garmin',rawHeading:120});
    currentPosition={lat:47.1,lon:15.4,heading:compass};
    sync3DOverlays();
    const bearing=captured['nd-gps-heading'].features[0].properties.bearing;
    currentPosition={lat:47.1,lon:15.4,heading:NaN};
    sync3DOverlays();
    const features=captured['nd-points'].features;
    return {bearing,hasGps:features.some(f=>f.properties.kind==='gps'),hasArrow:captured['nd-gps-heading'].features.length};
  })()`,context);
  assert.equal(gps.bearing,90);
  assert.equal(gps.hasGps,true);
  assert.equal(gps.hasArrow,0);
});

test('Android routing has shape-aware alternative returns and a historical overlap score', () => {
  const java = fs.readFileSync(path.resolve(__dirname,'../app/src/main/java/com/ndroutefinder/mobile/RouteEngine.java'),'utf8');
  const index = fs.readFileSync(path.resolve(__dirname,'../app/src/main/java/com/ndroutefinder/mobile/RouteHistory.java'),'utf8');
  assert.match(java,/eastShiftM/);
  assert.match(java,/returnRetraceRatio/);
  assert.match(java,/history\.overlapRatio\(track\.points\)/);
  assert.match(java,/Closest available route/);
  assert.match(index,/history_gpx_points\.csv/);
  assert.ok(fs.existsSync(path.resolve(__dirname,'../app/src/main/assets/history_gpx_points.csv.gz')));
});
