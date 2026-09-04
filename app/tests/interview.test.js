/* Tests for the interview screen's client.

   The script had none, and it carries decisions that no Python test can see:
   the digest that leaves the panel for the approval form, the seam where
   typed words stop being provisional, the reassembly of a frame the network
   cut in half. All of those can be deleted without a single one of the app's
   Python tests going red, which is the whole reason this file exists.

   No npm, no jsdom: `dom.js` next to this file is the page, and node's own
   `vm` is the realm. interview.js is loaded from disk exactly as it ships.

       node --test app/tests/interview.test.js
*/

"use strict";

const assert = require("node:assert");
const {test} = require("node:test");

const {load, page, streamed, refused, settled} = require("./dom.js");

/* Keyed like the pack, valued like nothing in it. These tests assert which
   string the client reached for, never how that string is worded, so a
   sentence rewritten in locales/ must not turn this file red. The keys are
   the contract, and they are FRAME_KEYS in routes/interview.py. */
const STRINGS = {
  said: "you-said", asked: "verbatim-asked",
  tool_call: "reads", tool_result: "answered", tool_failed: "refused",
  thinking: "waiting",
  stop_truncated: "cut", stop_max_tokens: "ceiling-of-tokens",
  stop_other: "other", stop_tool_use: "tool-use", stop_refusal: "refusal",
  stop_unknown: "stopped-saying {code}",
  ceiling: "gave-up-after {count}",
  error: "provider-said:",
  error_turn_running: "already-running", error_closed: "is-closed",
  error_not_configured: "no-engine", error_nothing_to_send: "nothing",
  error_gone: "not-on-disk", error_engine_failed: "engine-broke",
  error_bundle_broken: "bundle-broke", error_sheet_approved: "sheet-done",
  error_sheet_not_approved: "sheet-missing",
  error_nothing_to_revise: "nothing-to-revise",
  error_sheet_not_read: "no-sheet-in-that",
  error_draft_not_read: "no-post-in-that",
  error_unknown: "no-name-for",
  tokens: "{input} in, {output} out", spent: "{amount} USD"
};

function frame(fields) {
  return "data: " + JSON.stringify(fields) + "\n\n";
}

/* One turn, start to finish: what the person typed, what the network hands
   back, and the microtask hop that lets the client finish reading it. */
async function turn(screen, typed, chunks) {
  screen.reply = streamed(chunks);
  screen.at("text").value = typed;
  screen.at("say").dispatch("submit");
  await settled();
}

function opened(options) {
  return load(page(STRINGS, options));
}

const A_SHEET = {
  kind: "sheet", state: "proposed",
  angle: "The migration nobody asked for",
  elements: ["four months", "eleven services"],
  moment: "we shipped it on a Friday",
  conviction: "boring infrastructure is a feature",
  first_lines: ["Nobody thanked us.", "It was a Friday."],
  digest: "9f2c1ab04e6d7"
};

// ------------------------------------------------------------------ the sheet

test("a sheet frame fills the panel and moves the digest into the form",
     async () => {
  const screen = opened();
  await turn(screen, "go on", [frame(A_SHEET)]);

  assert.strictEqual(screen.at("sheet-digest").value, A_SHEET.digest);
  assert.strictEqual(screen.at("sheet").hidden, false);
  assert.strictEqual(screen.at("sheet-angle").textContent, A_SHEET.angle);
  assert.strictEqual(screen.at("sheet-moment").textContent, A_SHEET.moment);
  assert.strictEqual(screen.at("sheet-conviction").textContent,
                     A_SHEET.conviction);
  assert.deepStrictEqual(
    screen.at("sheet-elements").children.map((li) => li.textContent),
    A_SHEET.elements);
  assert.deepStrictEqual(
    screen.at("sheet-first-lines").children.map((li) => li.textContent),
    A_SHEET.first_lines);
});

test("a sheet with no digest empties the form rather than leaving the old one",
     async () => {
  /* A signature left behind would be a signature under text nobody read,
     which is the failure the digest exists to make impossible. */
  const screen = opened();
  await turn(screen, "go on", [frame(A_SHEET)]);
  assert.strictEqual(screen.at("sheet-digest").value, A_SHEET.digest);

  await turn(screen, "again", [frame(Object.assign({}, A_SHEET,
                                                   {digest: undefined}))]);
  assert.strictEqual(screen.at("sheet-digest").value, "");
});

test("a second sheet replaces the lists instead of growing them", async () => {
  const screen = opened();
  await turn(screen, "go on", [frame(A_SHEET)]);
  await turn(screen, "not that", [frame(Object.assign({}, A_SHEET, {
    elements: ["one line"], first_lines: ["Try this."],
    digest: "0000deadbeef"
  }))]);

  assert.deepStrictEqual(
    screen.at("sheet-elements").children.map((li) => li.textContent),
    ["one line"]);
  assert.deepStrictEqual(
    screen.at("sheet-first-lines").children.map((li) => li.textContent),
    ["Try this."]);
  assert.strictEqual(screen.at("sheet-digest").value, "0000deadbeef");
});

test("a sheet read out of prose says so, and a clean one stops saying it",
     async () => {
  /* The panel is the screen where somebody decides to sign. A sheet parsed
     out of an answer that ignored its tool is the weaker object, and the
     difference has to survive onto the live path, not only onto a reload. */
  const screen = opened();
  await turn(screen, "go on", [frame(Object.assign({}, A_SHEET, {
    problems: ["FIRST LINE carries 3 proposals and the sheet takes 2"]
  }))]);

  assert.strictEqual(screen.at("sheet-problems-block").hidden, false);
  assert.deepStrictEqual(
    screen.at("sheet-problems").children.map((li) => li.textContent),
    ["FIRST LINE carries 3 proposals and the sheet takes 2"]);

  await turn(screen, "again", [frame(A_SHEET)]);
  assert.strictEqual(screen.at("sheet-problems-block").hidden, true);
  assert.deepStrictEqual(screen.at("sheet-problems").children, []);
});

test("the approve form shows only while the sheet is proposed", async () => {
  const screen = opened();
  await turn(screen, "go on", [frame(A_SHEET)]);
  assert.strictEqual(screen.at("sheet-approve").hidden, false);

  await turn(screen, "yes", [frame(Object.assign({}, A_SHEET,
                                                 {state: "approved"}))]);
  assert.strictEqual(screen.at("sheet-approve").hidden, true);
});

// ------------------------------------------------------------- what was typed

test("what was typed stays in the box until a frame says it reached disk",
     async () => {
  const screen = opened();
  await turn(screen, "my answer", [frame({kind: "text", text: "hello"})]);

  assert.strictEqual(screen.at("text").value, "my answer");
  assert.deepStrictEqual(screen.thread(), ["verbatim-asked hello"]);
});

test("accepted commits what was typed and clears the box", async () => {
  const screen = opened();
  await turn(screen, "my answer", [
    frame({kind: "accepted"}),
    frame({kind: "text", text: "one "}),
    frame({kind: "text", text: "bubble"})
  ]);

  assert.strictEqual(screen.at("text").value, "");
  assert.deepStrictEqual(screen.thread(),
                         ["you-said my answer", "verbatim-asked one bubble"]);
});

test("a tool call between two answers opens a second bubble", async () => {
  /* The client drops `current` on every frame that is not text, so an answer
     resumed after a tool call must not be glued onto the first one. */
  const screen = opened();
  await turn(screen, "go", [
    frame({kind: "text", text: "before"}),
    frame({kind: "tool_call", name: "read_profile", arguments: {path: "p"}}),
    frame({kind: "text", text: "after"})
  ]);

  assert.deepStrictEqual(screen.thread(), [
    "verbatim-asked before",
    'reads read_profile {"path":"p"}',
    "verbatim-asked after"
  ]);
});

// ------------------------------------------------------------------- the wire

test("a frame cut in two by the network is reassembled", async () => {
  const whole = frame({kind: "text", text: "halved"});
  const cut = 18;
  const screen = opened();
  await turn(screen, "go", [whole.slice(0, cut), whole.slice(cut)]);

  assert.deepStrictEqual(screen.thread(), ["verbatim-asked halved"]);
});

test("a truncated tail is dropped without taking the turn down", async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "text", text: "kept"}),
                            'data: {"kind":"te']);

  assert.deepStrictEqual(screen.thread(), ["verbatim-asked kept"]);
  assert.strictEqual(screen.at("text").disabled, false);
});

// ---------------------------------------------------------------- the figures

test("usage shows the price when there is one", async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "usage", input_tokens: 1200,
                                   output_tokens: 34, price: 0.01234567})]);

  assert.strictEqual(screen.at("meter").textContent,
                     "1200 in, 34 out, 0.0123 USD");
});

test("usage shows tokens alone when the model has no price", async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "usage", input_tokens: 7,
                                   output_tokens: 8, price: null})]);

  assert.strictEqual(screen.at("meter").textContent, "7 in, 8 out");
});

// ----------------------------------------------------------------- the ending

test("a turn that ended normally writes no note", async () => {
  const screen = opened({awaiting: true});
  await turn(screen, "go", [frame({kind: "stop", stop: "end_turn",
                                   owing: false})]);

  assert.deepStrictEqual(screen.thread(), []);
  assert.strictEqual(screen.at("resume").hidden, true);
  assert.strictEqual(screen.at("awaiting").hidden, true);
});

test("a stop reason the pack knows renders its sentence", async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "stop", stop: "max_tokens",
                                   owing: true})]);

  assert.deepStrictEqual(screen.thread(), ["ceiling-of-tokens"]);
  assert.strictEqual(screen.at("resume").hidden, false);
  assert.strictEqual(screen.at("awaiting").hidden, false);
});

test("a stop reason the pack does not know never shows a bare token",
     async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "stop", stop: "recitation",
                                   owing: false})]);

  assert.deepStrictEqual(screen.thread(), ["stopped-saying recitation"]);
});

test("the ceiling says how many turns it gave up after", async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "ceiling", turns: 12, owing: true})]);

  assert.deepStrictEqual(screen.thread(), ["gave-up-after 12"]);
  assert.strictEqual(screen.at("resume").hidden, false);
});

// ---------------------------------------------------------------- the refusals

test("an error code the pack knows renders its sentence", async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "error", code: "sheet-approved"})]);

  assert.deepStrictEqual(screen.thread(), ["sheet-done"]);
});

test("an error code the pack does not know still carries the code",
     async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "error", code: "teapot"})]);

  assert.deepStrictEqual(screen.thread(), ["no-name-for teapot"]);
});

test("an error with no code is the provider's own words, kept", async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "error",
                                   technical: "ReadTimeout(30)"})]);

  assert.deepStrictEqual(screen.thread(), ["provider-said: ReadTimeout(30)"]);
});

test("an HTTP refusal renders the pack sentence for its detail", async () => {
  const screen = opened();
  screen.reply = refused(409, {detail: "turn-running"});
  screen.at("text").value = "go";
  screen.at("say").dispatch("submit");
  await settled();

  assert.deepStrictEqual(screen.thread(), ["already-running"]);
  /* Refused before anything was written, so the words stay in the box. */
  assert.strictEqual(screen.at("text").value, "go");
  assert.strictEqual(screen.at("text").disabled, false);
});

test("an HTTP refusal with no readable body falls back to the status",
     async () => {
  const screen = opened();
  screen.reply = refused(502, undefined);
  screen.at("text").value = "go";
  screen.at("say").dispatch("submit");
  await settled();

  assert.deepStrictEqual(screen.thread(), ["provider-said: 502"]);
});

// ------------------------------------------------------------- untrusted text

test("model text that looks like markup reaches the screen as text",
     async () => {
  const hostile = '<script>alert("x")</script>';
  const screen = opened();
  await turn(screen, "go", [frame({kind: "text", text: hostile})]);

  const bubble = screen.at("turns").children[0];
  assert.deepStrictEqual(screen.thread(), ["verbatim-asked " + hostile]);
  /* The page this suite renders on has no innerHTML at all, so the assertion
     above is not one path among two: it is the only path there is. */
  assert.throws(() => bubble.innerHTML, /not part of this DOM/);
});

test("a tool result that looks like markup reaches the screen as text",
     async () => {
  const hostile = "<img src=x onerror=1>";
  const screen = opened();
  await turn(screen, "go", [frame({kind: "tool_result", name: "read_file",
                                   result: hostile, is_error: true})]);

  const fold = screen.at("turns").children[0];
  assert.strictEqual(fold.open, true);
  assert.deepStrictEqual(screen.thread(), ["refused read_file " + hostile]);
});

// ------------------------------------------------------------ the affordances

test("resume sends an empty turn and leaves the box alone", async () => {
  const screen = opened({awaiting: true});
  screen.at("text").value = "half a thought";
  screen.reply = streamed([frame({kind: "text", text: "here"})]);
  screen.at("resume").dispatch("click");
  await settled();

  assert.strictEqual(screen.calls[0].init.body, "text=");
  assert.strictEqual(screen.at("text").value, "half a thought");
  assert.deepStrictEqual(screen.thread(), ["verbatim-asked here"]);
});

test("a seed puts its own text in the box", () => {
  const screen = opened({seeds: ["The migration nobody asked for"]});
  screen.document.querySelectorAll(".seed")[0].dispatch("click");

  assert.strictEqual(screen.at("text").value,
                     "The migration nobody asked for");
  assert.strictEqual(screen.at("text").focused, true);
});

test("the turn is a POST, which is the whole reason it is not an EventSource",
     async () => {
  const screen = opened();
  await turn(screen, "go", [frame({kind: "accepted"})]);

  assert.strictEqual(screen.calls[0].url, "/interview/2026-08-28-01/turn");
  assert.strictEqual(screen.calls[0].init.method, "POST");
  assert.strictEqual(screen.calls[0].init.body, "text=go");
});

test("an empty box sends nothing at all", () => {
  const screen = opened();
  screen.at("text").value = "   ";
  screen.at("say").dispatch("submit");

  assert.strictEqual(screen.calls.length, 0);
});

// ------------------------------------------------------- asking, and drafting

test("asking for the sheet posts where the button says, with no text",
     async () => {
  const screen = opened({ask: true});
  screen.reply = streamed([frame({kind: "text", text: "here it is"})]);
  screen.at("ask-sheet").dispatch("click");
  await settled();

  assert.strictEqual(screen.calls[0].url,
                     "/interview/2026-08-28-01/sheet/propose");
  assert.strictEqual(screen.calls[0].init.method, "POST");
  assert.strictEqual(screen.calls[0].init.body, "text=");
  assert.deepStrictEqual(screen.reloads, []);
});

test("the draft screen has no answer form, and the client survives it",
     async () => {
  const screen = opened({draft: true});
  screen.reply = streamed([frame({kind: "text", text: "writing"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.calls[0].url, "/interview/2026-08-28-01/draft");
  assert.deepStrictEqual(screen.thread(), ["verbatim-asked writing"]);
});

test("a draft that landed asks for the page again, once the stream is over",
     async () => {
  const screen = opened({draft: true});
  screen.reply = streamed([
    frame({kind: "draft", body: "Nobody thanked us.", verdicts: []}),
    frame({kind: "stop", stop: "end_turn", owing: false})
  ]);
  screen.at("write-draft").dispatch("click");

  /* Not mid stream: the turn is paid for, and cutting it to repaint sooner
     would throw away what was already bought. */
  assert.deepStrictEqual(screen.reloads, []);
  await settled();
  assert.deepStrictEqual(screen.reloads, [true]);
});

test("a drafting turn that lands nothing leaves the page where it is",
     async () => {
  const screen = opened({draft: true});
  screen.reply = streamed([
    frame({kind: "error", code: "sheet-not-approved"})
  ]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.deepStrictEqual(screen.reloads, []);
  assert.deepStrictEqual(screen.thread(), ["sheet-missing"]);
  assert.strictEqual(screen.at("write-draft").disabled, false);
});

test("a turn in flight disables every button that would start another",
     async () => {
  /* Every affordance on the fixture, deliberately: a screen that only ever
     had one of them would let the others drop out of `busy` unnoticed. That
     has already happened once here, to the write button. */
  const screen = opened({ask: true, draft: true, revision: true});
  screen.reply = streamed([frame({kind: "text", text: "one moment"})]);
  screen.at("ask-sheet").dispatch("click");

  assert.strictEqual(screen.at("ask-sheet").disabled, true);
  assert.strictEqual(screen.at("write-draft").disabled, true);
  assert.strictEqual(screen.at("revision").disabled, true);
  await settled();
  assert.strictEqual(screen.at("ask-sheet").disabled, false);
  assert.strictEqual(screen.at("write-draft").disabled, false);
  assert.strictEqual(screen.at("revision").disabled, false);
});


/* ------------------------------------------------------ the revision box */

test("the rewrite carries what is in the revision box", async () => {
  const screen = opened({draft: true, revision: true});
  screen.at("revision").value = "Ouvre sur le chiffre.";
  screen.reply = streamed([frame({kind: "accepted"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.calls[0].url, "/interview/2026-08-28-01/draft");
  assert.strictEqual(screen.calls[0].init.body,
                     "text=Ouvre+sur+le+chiffre.");
});

test("an empty box is a plain rewrite, not a refusal", async () => {
  const screen = opened({draft: true, revision: true});
  screen.reply = streamed([frame({kind: "accepted"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.calls.length, 1);
  assert.strictEqual(screen.calls[0].init.body, "text=");
});

test("the request leaves the box only once the server says it is on disk",
     async () => {
  const screen = opened({draft: true, revision: true});
  screen.at("revision").value = "Plus court.";
  screen.reply = refused(409, {detail: "nothing-to-revise"});
  screen.at("write-draft").dispatch("click");
  await settled();

  /* Refused before `accepted`: nothing was written, so the words stay where
     somebody can send them again. */
  assert.strictEqual(screen.at("revision").value, "Plus court.");
  assert.deepStrictEqual(screen.thread(), ["nothing-to-revise"]);

  screen.reply = streamed([frame({kind: "accepted"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.at("revision").value, "");
  assert.deepStrictEqual(screen.thread(),
                         ["nothing-to-revise", "you-said Plus court."]);
});

test("clearing the box never reaches the answer box, which is not there",
     async () => {
  /* An approved sheet takes the answer form off the page. A commit that
     assumed it was still there would throw inside the stream and take the
     rest of the turn with it. */
  const screen = opened({draft: true, revision: true});
  assert.strictEqual(screen.at("text"), null);
  screen.at("revision").value = "Autre angle.";
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "text", text: "rewriting"}),
    frame({kind: "stop", stop: "end_turn", owing: false})
  ]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.deepStrictEqual(screen.thread(),
                         ["you-said Autre angle.", "verbatim-asked rewriting"]);
});

/* The keyboard accelerator on the answer box.

   The interview screen is meant to feel like being asked something, not like
   filling a form, and the gesture that carries that is sending from the
   keyboard without reaching for a button. What is deliberately NOT done here
   is removing the button: this page posts its forms without JavaScript, and a
   form with no submit control is one a keyboard cannot send at all and a
   screen reader cannot announce. The accelerator is an addition. */

test("cmd+Enter sends the answer", async function () {
  const screen = opened();
  screen.reply = streamed([frame({kind: "said", text: "ok"})]);
  screen.at("text").value = "onze conversations";
  const prevented = screen.at("text").dispatch(
    "keydown", {key: "Enter", metaKey: true});
  await settled();
  assert.ok(prevented, "the newline has to be stopped");
  assert.equal(screen.calls.length, 1);
  assert.match(screen.calls[0].url, /\/turn$/);
});

test("ctrl+Enter sends it too, for a keyboard that has no cmd", async function () {
  const screen = opened();
  screen.reply = streamed([frame({kind: "said", text: "ok"})]);
  screen.at("text").value = "onze conversations";
  screen.at("text").dispatch("keydown", {key: "Enter", ctrlKey: true});
  await settled();
  assert.equal(screen.calls.length, 1);
});

test("a plain Enter types a newline and sends nothing", async function () {
  const screen = opened();
  screen.at("text").value = "onze conversations";
  const prevented = screen.at("text").dispatch("keydown", {key: "Enter"});
  await settled();
  assert.equal(prevented, false, "a paragraph break is a paragraph break");
  assert.equal(screen.calls.length, 0);
});

test("a modifier on another key sends nothing", async function () {
  const screen = opened();
  screen.at("text").value = "onze conversations";
  screen.at("text").dispatch("keydown", {key: "s", metaKey: true});
  await settled();
  assert.equal(screen.calls.length, 0);
});
