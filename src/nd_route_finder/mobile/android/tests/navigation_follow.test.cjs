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
