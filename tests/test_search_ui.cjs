const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {test} = require("node:test");

// Exercise the shipped script with delayed responses and browser page events.
function setup() {
  class Element {
    constructor() {
      this.events = {};
      this.children = [];
      this.attributes = {};
      this.hidden = true;
      this.value = "";
      this.classList = {toggle() {}};
    }
    addEventListener(name, callback) { this.events[name] = callback; }
    emit(name, values = {}) { return this.events[name]?.({preventDefault() {}, ...values}); }
    setAttribute(key, value) { this.attributes[key] = value; }
    removeAttribute(key) { delete this.attributes[key]; }
    replaceChildren() { this.children = []; }
    appendChild(child) { this.children.push(child); }
    querySelectorAll() { return this.children; }
    contains(element) { return this === element || this.children.includes(element); }
    click() { this.emit("click"); }
  }
  const input = new Element(), panel = new Element(), form = new Element();
  const submit = new Element(), status = new Element(), document = new Element();
  input.form = form;
  form.querySelector = () => submit;
  document.getElementById = id => ({"company-search": input, suggestions: panel, "search-status": status}[id]);
  document.createElement = () => new Element();
  const window = new Element();
  window.location = {assign(url) { window.destination = url; }};
  let timer;
  const pending = [];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/search.js"), "utf8"), {
    document, window, AbortController, encodeURIComponent,
    setTimeout(callback) { timer = callback; return 1; },
    clearTimeout() { timer = null; },
    fetch(url) { return new Promise(resolve => pending.push({url, resolve})); },
  });
  return {input, panel, form, submit, status, window, pending,
    type(value) { input.value = value; input.emit("input"); timer?.(); },
    async reply(index, items) {
      pending[index].resolve({ok: true, json: async () => items});
      await new Promise(resolve => setImmediate(resolve));
    }};
}

test("late autocomplete responses cannot replace a newer query", async () => {
  const ui = setup();
  ui.type("Mic");
  ui.type("Nvi");
  await ui.reply(1, [{name: "NVIDIA Corporation", symbol: "NVDA"}]);
  await ui.reply(0, [{name: "Microsoft Corporation", symbol: "MSFT"}]);
  assert.equal(ui.panel.children[0].textContent, "NVIDIA Corporation (NVDA)");
});

test("keyboard selection searches the ticker and shows progress", async () => {
  const ui = setup();
  ui.type("Mic");
  await ui.reply(0, [{name: "Microsoft Corporation", symbol: "MSFT"}]);
  ui.input.emit("keydown", {key: "ArrowDown"});
  ui.input.emit("keydown", {key: "Enter"});
  assert.equal(ui.window.destination, "/search?q=MSFT");
  assert.equal(ui.submit.disabled, true);
  assert.equal(ui.status.hidden, false);
});

test("returning to the page restores the Research button", () => {
  const ui = setup();
  ui.form.emit("submit");
  assert.equal(ui.submit.disabled, true);
  ui.window.emit("pageshow");
  assert.equal(ui.submit.disabled, false);
  assert.equal(ui.submit.textContent, "Research");
  assert.equal(ui.status.hidden, true);
});

test("Escape prevents an outstanding response from reopening suggestions", async () => {
  const ui = setup();
  ui.type("Mic");
  ui.input.emit("keydown", {key: "Escape"});
  await ui.reply(0, [{name: "Microsoft Corporation", symbol: "MSFT"}]);
  assert.equal(ui.panel.hidden, true);
  assert.equal(ui.panel.children.length, 0);
});
