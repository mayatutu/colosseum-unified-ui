// Exercise the shipped live-link code with fake transport and time; no network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const page = fs.readFileSync(path.join(__dirname, '..', 'eval_gui.html'), 'utf8');
const live = page.slice(page.indexOf('let lastBlob=null;'), page.indexOf("api('/api/config').then"));
let clock = 100, pending, requests = 0, polls = 0, posts = 0;
const nodes = new Map();
const sockets = [];
class Socket {
  constructor() { sockets.push(this); }
  close() {}
}
const context = vm.createContext({
  console, URL, AbortController, WebSocket: Socket,
  performance: {now: () => clock},
  location: {protocol: 'http:', host: 'localhost'}, STATION_BASE: '', STATION_KEY: 'test',
  ST: null, view: 'setup',
  $: selector => {
    if (!nodes.has(selector)) nodes.set(selector, {style: {}, textContent: '', hidden: true});
    return nodes.get(selector);
  },
  tr: value => value, stationURL: value => value,
  renderChecks() {}, renderRun() {}, renderPrompt() {}, mood() {}, renderPending() {},
  readDraft() {}, writeDraft() {}, blankRoundForm() {},
  loadResumable: async () => {},
  setInterval() {}, setTimeout: () => 1, clearTimeout() {},
  fetch: () => { requests++; return new Promise(resolve => { pending = resolve; }); },
});
vm.runInContext(live, context);
const run = code => vm.runInContext(code, context);
const state = step => ({run: {phase: 'running', step}, pending: [], recording: true});
(async () => {
  run('connect()');
  sockets[0].onmessage({data: JSON.stringify(state(1))});
  assert.equal(nodes.get('#connectionStatus').hidden, true);
  const delayed = run('refreshState()');
  run('refreshState()');
  assert.equal(requests, 1, 'Concurrent polls must coalesce');
  sockets[0].onmessage({data: JSON.stringify(state(2))});
  pending({ok: true, json: async () => state(0)});
  await delayed;
  assert.equal(context.ST.run.step, 2, 'Delayed HTTP must not replace newer WebSocket state');
  clock += 6000;
  run('updateConnectionStatus()');
  assert.equal(nodes.get('#phaseChip').textContent, 'Task status unknown');
  assert.match(nodes.get('#connectionStatus').textContent, /unknown/);
  const recovered = run('refreshState()');
  pending({ok: true, json: async () => state(3)});
  await recovered;
  assert.equal(context.ST.run.step, 3);
  assert.match(nodes.get('#connectionStatus').textContent, /status is current/);
  run('connect()');
  assert.equal(sockets[0].onmessage, null, 'Replaced sockets cannot publish stale state');

  // Run the actual stop handler, including its catch/finally chain.
  context.api = async () => { posts++; throw new TypeError('connection lost'); };
  context.TypeError = TypeError;
  context.toast = () => {};
  context.refreshState = async () => { polls++; };
  const handler = page.slice(page.indexOf('const stopRun='), page.indexOf("$('#killBtn').onclick"));
  run(handler);
  await run("stopRun('stopped')");
  assert.equal(posts, 1, 'Failed stop must not be resent');
  assert.equal(polls, 1, 'Failed stop must refresh status');
  console.log('PASS live state ordering, stale status, recovery, and stop without retry');
})().catch(error => { console.error(error); process.exitCode = 1; });
