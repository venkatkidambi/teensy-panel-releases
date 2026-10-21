const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('docs/app.js', 'utf8');
const data = {schema_version: 1, repository: 'venkatkidambi/teensy-panel-releases', stable: null, nightly: null, changelog: []};
function run(embedded, fetch) {
  const node = () => ({textContent: '', children: [], setAttribute() {},
    append(...children) {this.children.push(...children);},
    replaceChildren(...children) {this.children = children;}});
  const nodes = new Map(['release-status', 'release-channels', 'changelog-entries'].map(id => [id, node()]));
  if (embedded !== undefined) nodes.set('release-data', {textContent: embedded});
  const context = vm.createContext({URL, Intl, AbortSignal, fetch, document: {
    getElementById: id => nodes.get(id), createElement: node,
    createTextNode: text => ({textContent: text}),
  }});
  vm.runInContext(source, context);
  return nodes;
}

test('deployed page uses its bundled metadata without requesting cached JSON', () => {
  let requests = 0;
  const nodes = run(JSON.stringify(data), () => {requests++; throw Error('stale endpoint');});
  assert.equal(requests, 0);
  assert.equal(nodes.get('release-channels').children.length, 2);
  assert.equal(nodes.get('release-status').textContent, '');
});

test('unbuilt local page still loads releases.json', async () => {
  for (const embedded of [undefined, 'null']) {
    let requests = 0;
    const nodes = run(embedded, async url => {
      requests++;
      assert.equal(url, './releases.json');
      return {ok: true, json: async () => data};
    });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(requests, 1);
    assert.equal(nodes.get('release-channels').children.length, 2);
  }
});

test('invalid embedded metadata retains the GitHub download fallback', () => {
  let requests = 0;
  const nodes = run('{broken', () => {requests++;});
  assert.equal(requests, 0);
  assert.match(nodes.get('release-status').children[0].textContent, /could not be loaded/);
});
