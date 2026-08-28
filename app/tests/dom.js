/* A DOM small enough to read, so that interview.js can be tested unchanged.

   The repository is a Python project, and installing an npm ecosystem to
   exercise 291 lines of browser script would cost more than the script. So
   this is the node stdlib only: `vm` for the realm, and the handful of DOM
   surfaces the client actually touches. Anything it does not touch is absent
   on purpose, so reaching for something new fails loudly here instead of
   passing against a lie.

   `innerHTML` is the one absence that is a test in itself. The client's own
   header says everything from the model lands through textContent because
   innerHTML would make untrusted text into markup. Here innerHTML throws on
   read and on write, so a future edit that reaches for it cannot go green.
*/

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const encoder = new TextEncoder();

function Element(tag) {
  this.tagName = tag;
  this.children = [];
  this.parentNode = null;
  this.listeners = {};
  this.attributes = {};
  this.textContent = "";
  this.className = "";
  this.hidden = false;
  this.value = "";
  this.disabled = false;
  this.open = false;
  this.focused = false;
}

Object.defineProperty(Element.prototype, "firstChild", {
  get: function () { return this.children.length ? this.children[0] : null; }
});

/* Reading it is as much a mistake as writing it: a getter that returned
   markup would let a test claim a guarantee the browser does not give. */
Object.defineProperty(Element.prototype, "innerHTML", {
  get: function () { throw new Error("innerHTML is not part of this DOM"); },
  set: function () { throw new Error("innerHTML is not part of this DOM"); }
});

Element.prototype.appendChild = function (child) {
  child.parentNode = this;
  this.children.push(child);
  return child;
};

Element.prototype.removeChild = function (child) {
  const at = this.children.indexOf(child);
  if (at >= 0) { this.children.splice(at, 1); }
  child.parentNode = null;
  return child;
};

Element.prototype.remove = function () {
  if (this.parentNode) { this.parentNode.removeChild(this); }
};

Element.prototype.focus = function () { this.focused = true; };

Element.prototype.getAttribute = function (name) {
  return Object.prototype.hasOwnProperty.call(this.attributes, name)
    ? this.attributes[name] : null;
};

Element.prototype.setAttribute = function (name, value) {
  this.attributes[name] = String(value);
};

Element.prototype.addEventListener = function (type, handler) {
  (this.listeners[type] = this.listeners[type] || []).push(handler);
};

/* The test side of addEventListener. The event is the small object the
   client reads off it, nothing more. */
Element.prototype.dispatch = function (type) {
  let prevented = false;
  const event = {preventDefault: function () { prevented = true; }};
  (this.listeners[type] || []).forEach(function (handler) {
    handler(event);
  });
  return prevented;
};

function matches(node, selector) {
  return selector.charAt(0) === "."
    ? (" " + node.className + " ").indexOf(" " + selector.slice(1) + " ") >= 0
    : node.tagName === selector;
}

function walk(node, selector, found) {
  node.children.forEach(function (child) {
    if (matches(child, selector)) { found.push(child); }
    walk(child, selector, found);
  });
  return found;
}

Element.prototype.querySelectorAll = function (selector) {
  return walk(this, selector, []);
};

Element.prototype.querySelector = function (selector) {
  const found = walk(this, selector, []);
  return found.length ? found[0] : null;
};

/* What a reader would see. Leaves carry their own textContent; a node with
   children shows theirs, which is how the browser reads a turn built out of
   a label and a body. */
Element.prototype.read = function () {
  return this.children.length
    ? this.children.map(function (child) { return child.read(); }).join(" ")
    : this.textContent;
};

function Document() {
  this.body = new Element("body");
  this.ids = {};
}

Document.prototype.createElement = function (tag) {
  return new Element(tag);
};

Document.prototype.getElementById = function (id) {
  return Object.prototype.hasOwnProperty.call(this.ids, id)
    ? this.ids[id] : null;
};

Document.prototype.querySelectorAll = function (selector) {
  return this.body.querySelectorAll(selector);
};

/* Registers an element under an id and hangs it somewhere in the tree, the
   way a rendered template would. */
Document.prototype.place = function (parent, tag, id, fields) {
  const node = new Element(tag);
  Object.assign(node, fields || {});
  if (id) { this.ids[id] = node; }
  (parent || this.body).appendChild(node);
  return node;
};

/* A reply the client can drain. `chunks` are raw network reads, so a caller
   can cut one SSE frame in half and hand over the halves separately. */
function streamed(chunks) {
  const queue = chunks.map(function (chunk) { return encoder.encode(chunk); });
  let at = 0;
  return {
    ok: true,
    status: 200,
    body: {
      getReader: function () {
        return {
          read: function () {
            return Promise.resolve(at < queue.length
              ? {done: false, value: queue[at++]}
              : {done: true});
          }
        };
      }
    }
  };
}

/* An HTTP refusal: a status and a JSON body, no stream at all. Passing no
   body models a refusal whose body does not parse, which the client folds
   into an empty object rather than a failure of its own. */
function refused(status, body) {
  return {
    ok: false,
    status: status,
    json: function () {
      return body === undefined
        ? Promise.reject(new Error("not json"))
        : Promise.resolve(body);
    }
  };
}

/* Loads interview.js into a fresh realm over a fresh page. The path is
   resolved from this file, never from the working directory: the suite has
   to mean the same thing from anywhere in the repository. */
function load(page) {
  const source = fs.readFileSync(
    path.join(__dirname, "..", "verbatim_app", "static", "interview.js"),
    "utf8");
  const context = vm.createContext({
    document: page.document,
    fetch: page.fetch,
    location: page.location,
    TextDecoder: TextDecoder,
    URLSearchParams: URLSearchParams,
    console: console
  });
  vm.runInContext(source, context, {filename: "interview.js"});
  return page;
}

/* The interview screen as the template renders it, before a turn has run.
   Ids only, since the client addresses everything by id except the seed
   buttons and the form's own submit button. */
function page(strings, options) {
  const settings = options || {};
  const document = new Document();
  const calls = [];
  const reloads = [];
  const screen = {
    document: document,
    calls: calls,
    /* The client asks for the page again rather than painting a panel it
       would have to keep in step with the server. Counted, so a test can
       say when that happens and, more to the point, when it must not. */
    reloads: reloads,
    location: {reload: function () { reloads.push(true); }},
    /* What the next fetch resolves to. A test sets it before dispatching a
       submit, which is the only way a turn ever starts. */
    reply: null,
    fetch: function (url, init) {
      calls.push({url: url, init: init});
      const next = screen.reply;
      screen.reply = null;
      return next instanceof Error
        ? Promise.reject(next)
        : Promise.resolve(next);
    }
  };

  document.place(null, "pre", "meter", {textContent: "0 tokens in, 0 out"});
  document.place(null, "script", "verbatim-strings",
                 {textContent: JSON.stringify(strings)});
  document.place(null, "div", "turns");

  const sheet = document.place(null, "section", "sheet", {hidden: true});
  document.place(sheet, "dd", "sheet-angle");
  document.place(sheet, "ul", "sheet-elements");
  document.place(sheet, "dd", "sheet-moment");
  document.place(sheet, "dd", "sheet-conviction");
  document.place(sheet, "ul", "sheet-first-lines");
  const approve = document.place(sheet, "form", "sheet-approve",
                                 {hidden: true});
  document.place(approve, "input", "sheet-digest", {value: ""});

  document.place(null, "p", "awaiting", {hidden: !settings.awaiting});
  document.place(null, "button", "resume", {hidden: !settings.awaiting});

  if (settings.ask) {
    const ask = document.place(null, "button", "ask-sheet");
    ask.setAttribute("data-url", "/interview/2026-08-28-01/sheet/propose");
  }
  if (settings.draft) {
    const write = document.place(null, "button", "write-draft");
    write.setAttribute("data-url", "/interview/2026-08-28-01/draft");
  }

  /* An approved sheet ends the questions, so the screen that offers drafting
     has no answer form on it at all. The client has to survive that. */
  if (!settings.draft) {
    const form = document.place(null, "form", "say",
                                {action: "/interview/2026-08-28-01/turn"});
    document.place(form, "textarea", "text");
    document.place(form, "button", null, {textContent: "Send"});
  }

  (settings.seeds || []).forEach(function (text) {
    const seed = document.place(null, "button", null, {className: "seed"});
    seed.setAttribute("data-text", text);
  });

  screen.at = function (id) { return document.getElementById(id); };
  /* Every turn in the thread, in order, as a reader would read it. */
  screen.thread = function () {
    return document.getElementById("turns").children
      .map(function (turn) { return turn.read(); });
  };
  return screen;
}

/* Everything in this harness resolves without a timer, and the microtask
   queue drains fully before the next macrotask, so one hop through the
   macrotask queue is enough to let a whole turn finish. */
function settled() {
  return new Promise(function (resolve) { setImmediate(resolve); });
}

module.exports = {load, page, streamed, refused, settled};
