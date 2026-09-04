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
  sheet_first_line_none: "neither-of-these",
  sufficiency: "material {ratio}%",
  sufficiency_counts: "{facts}/{enough} facts, {figures} num, {named} named",
  tool_call: "reads", tool_result: "answered", tool_failed: "refused",
  tool_fold: "engine-did {count}",
  tool_fold_failed: "engine-did {count} refused {failed}",
  thinking: "waiting",
  waiting_sheet: "putting-the-sheet-together",
  waiting_post: "writing-your-post",
  waiting_finishing: "finishing",
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

/* The proposed first lines as a reader sees them: the label text, with the
   radio that carries the choice left out. */
function lines(screen) {
  return screen.at("sheet-first-lines").children
    .map((li) => li.read().trim())
    .filter((text) => text !== STRINGS.sheet_first_line_none);
}

/* Every choice the panel offers, as the values that would be submitted. */
function choices(screen) {
  return screen.at("sheet-first-lines").querySelectorAll("input")
    .map((node) => node.getAttribute("value"));
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
  assert.deepStrictEqual(lines(screen), A_SHEET.first_lines);
});


/* ------------------------------------------ the first line, on the live path */

test("a sheet arriving mid stream offers the choice, refusal included",
     async () => {
  /* F1 on the wire. The panel is filled by the client when a sheet lands
     without a reload, so a choice that only existed in the template would
     be a step that vanishes on exactly the path everybody takes. */
  const screen = opened();
  await turn(screen, "go on", [frame(A_SHEET)]);

  assert.deepStrictEqual(choices(screen), ["0", "1", "none"]);
  assert.deepStrictEqual(lines(screen), A_SHEET.first_lines);
});

test("an approved sheet arriving offers no choice, like the template",
     async () => {
  /* Frozen. A radio that changes nothing is a lie, and the template gates
     on the same field. */
  const screen = opened();
  await turn(screen, "go on",
             [frame(Object.assign({}, A_SHEET, {state: "approved"}))]);

  assert.deepStrictEqual(choices(screen), []);
});

test("the choice travels with the approval form and is required",
     async () => {
  const screen = opened();
  await turn(screen, "go on", [frame(A_SHEET)]);

  const radio = screen.at("sheet-first-lines").querySelectorAll("input")[0];
  assert.strictEqual(radio.getAttribute("type"), "radio");
  assert.strictEqual(radio.getAttribute("name"), "first_line");
  assert.strictEqual(radio.getAttribute("form"), "sheet-approve");
  assert.strictEqual(radio.getAttribute("required"), "required");
});

test("a second sheet replaces the choice instead of adding to it",
     async () => {
  const screen = opened();
  await turn(screen, "go on", [frame(A_SHEET)]);
  await turn(screen, "not that", [frame(Object.assign({}, A_SHEET, {
    first_lines: ["Try this."], digest: "0000deadbeef"
  }))]);

  assert.deepStrictEqual(choices(screen), ["0", "none"]);
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
  assert.deepStrictEqual(lines(screen), ["Try this."]);
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
    'engine-did 1 reads read_profile {"path":"p"}',
    "verbatim-asked after"
  ]);
});

test("a run of tool traffic is one fold, closed, holding all of it",
     async () => {
  /* The complaint this answers: the engine reading four files in order to
     be able to ask one question printed a dozen blocks between somebody's
     words and the question they were read for. Folded, nothing is dropped
     and the question is next to the sentence it answers. */
  const screen = opened();
  await turn(screen, "go", [
    frame({kind: "tool_call", name: "read_instance", arguments: {path: "a"}}),
    frame({kind: "tool_call", name: "read_instance", arguments: {path: "b"}}),
    frame({kind: "tool_result", name: "read_instance", result: "A"}),
    frame({kind: "tool_result", name: "read_instance", result: "B"}),
    frame({kind: "text", text: "and so my question"})
  ]);

  const [fold, said] = screen.at("turns").children;
  assert.strictEqual(fold.open, false);
  assert.strictEqual(fold.children[0].textContent, "engine-did 2");
  assert.strictEqual(fold.children[1].children.length, 4);
  assert.strictEqual(said.read(), "verbatim-asked and so my question");
});

test("words after a run start a second fold rather than joining the first",
     async () => {
  /* The boundary is any frame that is not tool traffic, which is the rule
     `interview.runs` folds the replay on. Two arrivals of one conversation
     breaking in different places would mean a reload rewrote the screen. */
  const screen = opened();
  await turn(screen, "go", [
    frame({kind: "tool_call", name: "read_instance", arguments: {}}),
    frame({kind: "text", text: "thinking"}),
    frame({kind: "tool_call", name: "read_instance", arguments: {}})
  ]);

  assert.deepStrictEqual(
    screen.at("turns").children.map((node) => node.children[0].textContent),
    ["engine-did 1", "verbatim-asked", "engine-did 1"]);
});

test("a figure about the bill does not end a run", async () => {
  /* Usage frames arrive mid turn and say nothing about what the engine is
     doing, so a run cut in two by one would count the same work twice. */
  const screen = opened();
  await turn(screen, "go", [
    frame({kind: "tool_call", name: "read_instance", arguments: {}}),
    frame({kind: "usage", input_tokens: 10, output_tokens: 2, price: null}),
    frame({kind: "tool_result", name: "read_instance", result: "ok"})
  ]);

  assert.strictEqual(screen.at("turns").children.length, 1);
  assert.strictEqual(screen.at("turns").children[0].children[0].textContent,
                     "engine-did 1");
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

  /* The run stays closed carrying a refusal; the refusal inside it does not,
     so opening the one line lands on the thing that went wrong. */
  const fold = screen.at("turns").children[0];
  assert.strictEqual(fold.open, false);
  assert.strictEqual(fold.children[1].children[0].open, true);
  assert.deepStrictEqual(screen.thread(),
                         ["engine-did 1 refused 1 refused read_file " + hostile]);
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
  /* In the draft panel, like every drafting turn. The thread above is the
     interview, and an approved sheet has ended it. */
  assert.deepStrictEqual(screen.panel(), ["verbatim-asked writing"]);
  assert.deepStrictEqual(screen.thread(), []);
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
  assert.deepStrictEqual(screen.panel(), ["sheet-missing"]);
  assert.strictEqual(screen.at("write-draft").disabled, false);
});




test("the sheet button appears with the first words that reach disk",
     async () => {
  /* The server refuses a sheet before anybody has said anything, so the
     screen does not offer one. The page does not reload between two
     interview turns, so the frame that says the words are on disk is what
     puts the button up. */
  const screen = opened({ask: true, asked: false});
  assert.strictEqual(screen.at("ask-sheet").hidden, true);
  assert.strictEqual(screen.at("ask-sheet-hint").hidden, true);

  await turn(screen, "j'ai arrete les agences", [
    frame({kind: "accepted"}),
    frame({kind: "text", text: "When?"})
  ]);

  assert.strictEqual(screen.at("ask-sheet").hidden, false);
  assert.strictEqual(screen.at("ask-sheet-hint").hidden, false);
});

test("a turn refused before it was written leaves the button hidden",
     async () => {
  const screen = opened({ask: true, asked: false});
  screen.reply = refused(409, {detail: "turn-running"});
  screen.at("text").value = "j'ai arrete les agences";
  screen.at("say").dispatch("submit");
  await settled();

  assert.strictEqual(screen.at("ask-sheet").hidden, true);
});




/* ------------------------------------ a half typed request outlives the page */

test("what is typed in the revision box is kept as it is typed", async () => {
  const screen = opened({draft: true, revision: true});
  screen.at("revision").value = "trop vague, mets le vrai chiffre";
  screen.at("revision").dispatch("input");

  assert.strictEqual(screen.store.kept["verbatim:revision:2026-08-28-01"],
                     "trop vague, mets le vrai chiffre");
});

test("a request kept from last time is in the box on the next page",
     async () => {
  const screen = opened({
    draft: true, revision: true,
    storage: {seeded: {"verbatim:revision:2026-08-28-01": "plus court"}}
  });
  assert.strictEqual(screen.at("revision").value, "plus court");
});

test("another interview's draft never lands in this box", async () => {
  const screen = opened({
    draft: true, revision: true,
    storage: {seeded: {"verbatim:revision:2026-08-28-99": "someone else"}}
  });
  assert.strictEqual(screen.at("revision").value, "");
});

test("the box is emptied once the request is on disk, here and in the store",
     async () => {
  const screen = opened({
    draft: true, revision: true,
    storage: {seeded: {"verbatim:revision:2026-08-28-01": "plus court"}}
  });
  screen.reply = streamed([frame({kind: "accepted"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.at("revision").value, "");
  assert.strictEqual(
    screen.store.kept["verbatim:revision:2026-08-28-01"], undefined);
});

test("a request refused before it was written is still there afterwards",
     async () => {
  const screen = opened({draft: true, revision: true});
  screen.at("revision").value = "plus court";
  screen.at("revision").dispatch("input");
  screen.reply = refused(409, {detail: "nothing-to-revise"});
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.at("revision").value, "plus court");
  assert.strictEqual(screen.store.kept["verbatim:revision:2026-08-28-01"],
                     "plus court");
});

test("the passage it was aimed at comes back with it", async () => {
  const screen = opened({
    draft: true, revision: true,
    blocks: [{digest: "aaa1", text: "Un bloc."},
             {digest: "bbb2", text: "Un autre."}],
    storage: {seeded: {
      "verbatim:revision:2026-08-28-01": "trop vague",
      "verbatim:scope:2026-08-28-01": "1:bbb2"
    }}
  });
  assert.strictEqual(screen.at("revision-scope").value, "1");
  assert.strictEqual(screen.at("revision-echo").hidden, false);
  assert.strictEqual(screen.at("revision-scope-line").hidden, false);
});

test("a passage the post no longer has does not come back", async () => {
  /* The digest is the staleness guard everywhere else, and it is the same
     guard here: a turn can have rewritten that block since, and a picker
     restored onto its index would aim the next request at other words. */
  const screen = opened({
    draft: true, revision: true,
    blocks: [{digest: "aaa1", text: "Un bloc."},
             {digest: "changed", text: "Un autre, reecrit."}],
    storage: {seeded: {"verbatim:scope:2026-08-28-01": "1:bbb2"}}
  });
  assert.strictEqual(screen.at("revision-scope").value, "");
  assert.strictEqual(screen.at("revision-echo").hidden, true);
});

test("a scope the server already chose is not overruled by a kept one",
     async () => {
  /* `pending_scope` puts back the block of a request still waiting for an
     answer, and it reads the disk. What is kept here is a browser's, and it
     only ever fills a gap. */
  const screen = opened({
    draft: true, revision: true, scope: "0",
    blocks: [{digest: "aaa1", text: "Un bloc."},
             {digest: "bbb2", text: "Un autre."}],
    storage: {seeded: {"verbatim:scope:2026-08-28-01": "1:bbb2"}}
  });
  assert.strictEqual(screen.at("revision-scope").value, "0");
});

test("a browser that refuses to store anything still works", async () => {
  /* A private window, blocked site data, a thumbnail renderer: the accessor
     itself throws. Losing the convenience is fine and losing the screen is
     not. */
  const screen = opened({draft: true, revision: true,
                         storage: {broken: true}});
  screen.at("revision").value = "plus court";
  screen.at("revision").dispatch("input");

  screen.reply = streamed([frame({kind: "accepted"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.calls.length, 1);
  assert.strictEqual(screen.at("revision").value, "");
});


/* ----------------------------------------- the waiting line follows the turn */

test("the waiting line survives the first byte and waits for the answer",
     async () => {
  /* It used to go the moment the response headers arrived, which is before
     the model has said anything: the gap it exists to cover was the one it
     was removed for. */
  const screen = opened();
  screen.reply = streamed([frame({kind: "accepted"})], {hold: true});
  screen.at("text").value = "j'ai arrete les agences";
  screen.at("say").dispatch("submit");
  await settled();

  assert.deepStrictEqual(screen.thread(), ["you-said j'ai arrete les agences",
                                           "waiting"]);
});

test("the line says which phase the turn is in, and says it last",
     async () => {
  const screen = opened({ask: true, asked: false});
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "tool_call", name: "propose_sheet", phase: "sheet",
           arguments: {}})
  ], {hold: true});
  screen.at("ask-sheet").dispatch("click");
  await settled();

  const thread = screen.thread();
  assert.strictEqual(thread[thread.length - 1], "putting-the-sheet-together");
});

test("a post being written says so, and finishing says that", async () => {
  const screen = opened({draft: true, revision: true});
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "tool_call", name: "propose_draft", phase: "post",
           arguments: {}})
  ], {hold: true});
  screen.at("write-draft").dispatch("click");
  await settled();

  let shown = screen.panel();
  assert.strictEqual(shown[shown.length - 1], "writing-your-post");

  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "tool_call", name: "propose_draft", phase: "post",
           arguments: {}}),
    frame({kind: "draft", body: "Quatre mois.", verdicts: []})
  ], {hold: true});
  screen.at("write-draft").dispatch("click");
  await settled();

  shown = screen.panel();
  assert.strictEqual(shown[shown.length - 1], "finishing");
});

test("a phase the pack has no words for shows nothing rather than a token",
     async () => {
  /* The language leak in miniature, and the rule the stop reasons already
     follow: a bare `compiling` on a French screen is worse than no line. */
  const screen = opened({ask: true, asked: false});
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "tool_call", name: "read_file", phase: "", arguments: {}})
  ], {hold: true});
  screen.at("ask-sheet").dispatch("click");
  await settled();

  assert.strictEqual(screen.thread().indexOf("waiting_"), -1);
  assert.strictEqual(screen.thread().indexOf("undefined"), -1);
});

test("the line is gone once the turn is over", async () => {
  const screen = opened();
  await turn(screen, "j'ai arrete", [
    frame({kind: "accepted"}),
    frame({kind: "text", text: "When?"}),
    frame({kind: "stop", stop: "end_turn", owing: false})
  ]);

  assert.deepStrictEqual(screen.thread(),
                         ["you-said j'ai arrete", "verbatim-asked When?"]);
});

test("an answer arriving takes the line away rather than pushing it down",
     async () => {
  /* While words are streaming the words are the signal, and a status line
     under them saying the model is thinking says something untrue. */
  const screen = opened();
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "text", text: "When?"})
  ], {hold: true});
  screen.at("text").value = "j'ai arrete";
  screen.at("say").dispatch("submit");
  await settled();

  assert.deepStrictEqual(screen.thread(),
                         ["you-said j'ai arrete", "verbatim-asked When?"]);
});


/* ------------------------------------------------ how much is on the table */

test("the frame that says the words are on disk moves the gauge", async () => {
  /* It reads what the person said, so it moves on the frame that says what
     they said reached disk, and on no earlier one: a number drawn for words
     still liable to be refused is a number that then has to be taken back. */
  const screen = opened();
  await turn(screen, "12 clients chez Malt", [
    frame({kind: "accepted", facts: 2, figures: 1, named: 1, ratio: 25,
           enough: 8}),
    frame({kind: "text", text: "When?"})
  ]);

  assert.strictEqual(screen.at("sufficiency-ratio").textContent,
                     "material 25%");
  assert.strictEqual(screen.at("sufficiency-counts").textContent,
                     "2/8 facts, 1 num, 1 named");
});

test("a turn refused before it was written leaves the gauge alone",
     async () => {
  const screen = opened();
  screen.at("sufficiency-ratio").textContent = "material 25%";
  screen.reply = refused(409, {detail: "turn-running"});
  screen.at("text").value = "12 clients chez Malt";
  screen.at("say").dispatch("submit");
  await settled();

  assert.strictEqual(screen.at("sufficiency-ratio").textContent,
                     "material 25%");
});

test("an accepted frame with no gauge on it leaves the line where it is",
     async () => {
  /* Older frames, and any path that ever stops sending the counts. A line
     rewritten from missing numbers reads as a gauge that fell to zero. */
  const screen = opened();
  screen.at("sufficiency-ratio").textContent = "material 25%";
  await turn(screen, "encore", [frame({kind: "accepted"})]);

  assert.strictEqual(screen.at("sufficiency-ratio").textContent,
                     "material 25%");
});


/* ------------------------------------- a drafting turn answers in its panel */

test("what the engine says about a revision lands in the revision panel",
     async () => {
  /* The defect this exists to refuse, seen in Alchie: the refusal shows up
     in the general channel at the top of the page while the scope, the
     echo of the passage and the box are all in the panel further down. The
     answer belongs where the question was asked. */
  const screen = opened({draft: true, revision: true});
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "text", text: "Give me the name and the year."}),
    frame({kind: "stop", stop: "end_turn", owing: false})
  ]);
  screen.at("revision").value = "Ces fourchettes viennent d'ou ?";
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.deepStrictEqual(
    screen.panel(),
    ["you-said Ces fourchettes viennent d'ou ?",
     "verbatim-asked Give me the name and the year."]);
  assert.deepStrictEqual(screen.thread(), []);
  assert.strictEqual(screen.at("revision-reply").hidden, false);
});

test("what a tool answered stays in the panel with the rest of the turn",
     async () => {
  /* Every drafting turn calls a tool, so every drafting turn has one of
     these. A refused rewrite renders it open, so the loudest half of a
     refusal was the half displayed a screen away from its own question. */
  const screen = opened({draft: true, revision: true});
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "tool_call", name: "rewrite_passage", phase: "post",
           arguments: {}}),
    frame({kind: "tool_result", name: "rewrite_passage",
           result: "that passage has changed", is_error: true}),
    frame({kind: "text", text: "Read the post again."})
  ]);
  screen.at("revision").value = "trop long";
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.deepStrictEqual(screen.thread(), []);
  /* The status line, the run its call and answer fold into, and the words. */
  assert.strictEqual(screen.panel().length, 3);
});

test("a drafting turn that fails says so in the panel too", async () => {
  const screen = opened({draft: true, revision: true});
  screen.reply = streamed([frame({kind: "error", code: "passage-gone"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.deepStrictEqual(screen.thread(), []);
  assert.strictEqual(screen.panel().length, 1);
});

test("the next request clears the last answer rather than stacking on it",
     async () => {
  const screen = opened({draft: true, revision: true});
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "text", text: "Which source?"})
  ]);
  screen.at("revision").value = "premiere demande";
  screen.at("write-draft").dispatch("click");
  await settled();

  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "text", text: "Thank you."})
  ]);
  screen.at("revision").value = "barometre Malt, 2025";
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.deepStrictEqual(
    screen.panel(),
    ["you-said barometre Malt, 2025", "verbatim-asked Thank you."]);
});

test("the scope of the refused request is still the scope of the answer",
     async () => {
  /* The other half of the Alchie defect: its refusal left the panel, and
     answering it meant picking the passage again by hand. Nothing reloads
     on a turn that landed nothing, so the picker is still on the block. */
  const screen = opened({draft: true, revision: true,
                         blocks: [{digest: "aaa1", text: "Un bloc."},
                                  {digest: "bbb2", text: "Un autre."}]});
  screen.at("revision-scope").value = "1";
  screen.at("revision").value = "trop vague";
  screen.reply = streamed([
    frame({kind: "accepted"}),
    frame({kind: "text", text: "Which source?"})
  ]);
  screen.at("write-draft").dispatch("click");
  await settled();

  screen.at("revision").value = "barometre Malt, 2025";
  screen.reply = streamed([frame({kind: "accepted"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.calls[1].init.body,
                     "text=barometre+Malt%2C+2025&passage=bbb2&passage_index=1");
  assert.deepStrictEqual(screen.reloads, []);
});

test("the interview thread is still where an interview turn goes",
     async () => {
  /* The panel is for the drafting loop and for nothing else. A screen that
     routed every turn there would empty the thread the anchoring source is
     read from. */
  const screen = opened();
  await turn(screen, "j'ai arrete les agences", [
    frame({kind: "accepted"}),
    frame({kind: "text", text: "When?"})
  ]);

  assert.deepStrictEqual(
    screen.thread(),
    ["you-said j'ai arrete les agences", "verbatim-asked When?"]);
  assert.deepStrictEqual(screen.panel(), []);
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
     somebody can send them again. Read off the panel, which is where a
     drafting turn talks: the request was typed there and the scope is there. */
  assert.strictEqual(screen.at("revision").value, "Plus court.");
  assert.deepStrictEqual(screen.panel(), ["nothing-to-revise"]);

  screen.reply = streamed([frame({kind: "accepted"})]);
  screen.at("write-draft").dispatch("click");
  await settled();

  assert.strictEqual(screen.at("revision").value, "");
  assert.deepStrictEqual(screen.panel(), ["you-said Plus court."]);
  assert.deepStrictEqual(screen.thread(), []);
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

  assert.deepStrictEqual(screen.panel(),
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

/* Aiming a revision at one passage.

   The three things the panel has to do, and none of them is decoration: the
   exact passage is echoed so somebody sees the text that will be replaced
   rather than a description of where it is; the field teaches by example
   rather than naming itself; and the scope sits on the action line, which is
   the sentence read with a hand already on the button.

   What travels is the index and the digest. The index says which block, the
   digest says this page was not stale, and the server refuses on the second
   rather than landing the request on whatever is there now. */

const BLOCKS = [
  {digest: "aaaaaaaaaaaaaaaa", text: "Quatre mois à vendre aux agences."},
  {digest: "bbbbbbbbbbbbbbbb", text: "Onze conversations, deux propositions."}
];

function withBlocks() {
  return load(page(STRINGS, {draft: true, revision: true, blocks: BLOCKS}));
}

test("choosing a passage echoes it word for word", async function () {
  const screen = withBlocks();
  screen.at("revision-scope").value = "1";
  screen.at("revision-scope").dispatch("change");
  assert.equal(screen.at("revision-echo").textContent, BLOCKS[1].text);
  assert.equal(screen.at("revision-echo").hidden, false);
  assert.equal(screen.at("revision-scope-line").hidden, false);
});

test("going back to the whole post takes the echo away", async function () {
  const screen = withBlocks();
  screen.at("revision-scope").value = "0";
  screen.at("revision-scope").dispatch("change");
  screen.at("revision-scope").value = "";
  screen.at("revision-scope").dispatch("change");
  assert.equal(screen.at("revision-echo").hidden, true);
  assert.equal(screen.at("revision-scope-line").hidden, true);
});

test("the request carries the index and the digest", async function () {
  const screen = withBlocks();
  screen.reply = streamed([frame({kind: "draft", body: "ok", anchors: []})]);
  screen.at("revision").value = "Trop vague, mets le vrai chiffre.";
  screen.at("revision-scope").value = "1";
  screen.at("revision-scope").dispatch("change");
  screen.at("write-draft").dispatch("click");
  await settled();
  const sent = new URLSearchParams(screen.calls[0].init.body);
  assert.equal(sent.get("passage"), BLOCKS[1].digest);
  assert.equal(sent.get("passage_index"), "1");
  assert.equal(sent.get("text"), "Trop vague, mets le vrai chiffre.");
});

test("a request about the whole post carries no scope", async function () {
  const screen = withBlocks();
  screen.reply = streamed([frame({kind: "draft", body: "ok", anchors: []})]);
  screen.at("revision").value = "Plus court.";
  screen.at("write-draft").dispatch("click");
  await settled();
  const sent = new URLSearchParams(screen.calls[0].init.body);
  assert.equal(sent.get("passage"), null);
  assert.equal(sent.get("passage_index"), null);
});

test("the picker is read at the click, not when it moved", async function () {
  /* Somebody chooses a passage, types, then changes their mind about which
     one. What travels is the one in front of them when they press it. */
  const screen = withBlocks();
  screen.reply = streamed([frame({kind: "draft", body: "ok", anchors: []})]);
  screen.at("revision").value = "Trop vague.";
  screen.at("revision-scope").value = "1";
  screen.at("revision-scope").dispatch("change");
  screen.at("revision-scope").value = "0";
  screen.at("revision-scope").dispatch("change");
  screen.at("write-draft").dispatch("click");
  await settled();
  assert.equal(new URLSearchParams(screen.calls[0].init.body).get("passage"),
               BLOCKS[0].digest);
});
