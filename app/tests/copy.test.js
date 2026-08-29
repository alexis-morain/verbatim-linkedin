/* Tests for the copy buttons.

   The script is small and two of its decisions are not. It copies an element
   the server wrote rather than the document rendered beside it, which on a
   post screen is the difference between the post and the post plus every
   interview sentence the session recorded. And it never says a copy
   happened when the browser refused one, which is the same rule the
   publishing screen learned the hard way.

       node --test app/tests/copy.test.js
*/

"use strict";

const assert = require("node:assert");
const {test} = require("node:test");

const {load, copyPage, settled} = require("./dom.js");

const POST = "A hook.\n\nThe post, with a **bold** run.\n\nNadia Feriel, CFO.";

function opened(items, options) {
  return load(copyPage(items, options));
}

function one(options) {
  return opened([{source: "post-text", text: POST, label: "Copy the post",
                  done: "Copied", failed: "Not copied",
                  failedHint: "Select it and copy it by hand."}], options);
}

/* The sentence beside a button, when there is one. */
function said(screen, source) {
  const slot = screen.document.getElementById(source + "-slot");
  const found = slot ? slot.querySelector(".copy-said") : null;
  return found && !found.hidden ? found.textContent : null;
}

async function click(screen, source) {
  screen.button(source).dispatch("click");
  await settled();
}

test("a button appears for every payload, labelled by the pack", function () {
  const screen = opened([
    {source: "document-markdown", text: "# Doc", label: "Copy the markdown"},
    {source: "document-text", text: "Doc", label: "Copy as plain text",
     hidden: true}
  ]);
  assert.equal(screen.buttons().length, 2);
  assert.equal(screen.button("document-markdown").textContent,
               "Copy the markdown");
  assert.equal(screen.button("document-text").textContent,
               "Copy as plain text");
});

test("the button is a button, not a form submit", function () {
  assert.equal(one().button("post-text").getAttribute("type"), "button");
});

test("clicking copies the payload the server wrote", async function () {
  const screen = one();
  await click(screen, "post-text");
  assert.deepEqual(screen.written, [POST]);
});

test("what is copied comes from the payload, never from a neighbour",
     async function () {
  /* The whole point on a post screen. If this ever reads a rendered node
     instead, the session notes go out with the post. */
  const screen = one();
  screen.document.place(null, "div", "rendered",
                        {textContent: "A hook. The post, with a bold run."});
  await click(screen, "post-text");
  assert.deepEqual(screen.written, [POST]);
});

test("a payload edited after the page loaded is copied as it now stands",
     async function () {
  const screen = one();
  screen.at("post-text").textContent = "Rewritten by another tab.";
  await click(screen, "post-text");
  assert.deepEqual(screen.written, ["Rewritten by another tab."]);
});

test("two payloads on one page stay apart", async function () {
  const screen = opened([
    {source: "document-markdown", text: "# Doc", label: "md"},
    {source: "document-text", text: "Doc", label: "txt", hidden: true}
  ]);
  await click(screen, "document-text");
  assert.deepEqual(screen.written, ["Doc"]);
  await click(screen, "document-markdown");
  assert.deepEqual(screen.written, ["Doc", "# Doc"]);
});

test("a slot naming a payload that is not there makes no button", function () {
  /* A template edited in one place and not the other. A button that copied
     nothing, or the empty string, would be worse than no button. */
  const screen = opened([{source: "gone", label: "Copy", slotOnly: true}]);
  assert.equal(screen.buttons().length, 0);
});

test("a page with no slot on it makes no button", function () {
  assert.equal(opened([]).buttons().length, 0);
});

test("no clipboard means no button at all", function () {
  /* A page served from anything but loopback or https has none, and a dead
     button is worse than no button: the text is still there to select. */
  const screen = one({noClipboard: true});
  assert.equal(screen.buttons().length, 0);
});

test("a copy that worked says so, then goes back to its label",
     async function () {
  const screen = one();
  await click(screen, "post-text");
  assert.equal(screen.button("post-text").textContent, "Copied");
  assert.equal(screen.pending().length, 1);
  screen.fire();
  assert.equal(screen.button("post-text").textContent, "Copy the post");
});

test("a copy the browser refused says so and keeps saying so",
     async function () {
  /* writeText rejects when the document is not focused or permission is
     denied. A button that went back to reading Copy would be claiming a copy
     that never happened. */
  const screen = one({refuses: true});
  await click(screen, "post-text");
  assert.equal(screen.button("post-text").textContent, "Not copied");
  assert.deepEqual(screen.written, []);
  assert.equal(screen.pending().length, 0);
});

test("the word goes in the button and the sentence goes beside it",
     async function () {
  /* A paragraph written into a button's own text is a button the width of a
     paragraph, and the failure is the moment somebody needs both. */
  const screen = one({refuses: true});
  assert.equal(said(screen, "post-text"), null);
  await click(screen, "post-text");
  assert.equal(screen.button("post-text").textContent, "Not copied");
  assert.equal(said(screen, "post-text"), "Select it and copy it by hand.");
});

test("a copy that works afterwards takes the sentence back down",
     async function () {
  const screen = one({refuses: true});
  await click(screen, "post-text");
  assert.notEqual(said(screen, "post-text"), null);
  screen.refuses = false;
  await click(screen, "post-text");
  assert.equal(screen.button("post-text").textContent, "Copied");
  assert.equal(said(screen, "post-text"), null);
});

test("a refusal opens the text so it can be copied by hand", async function () {
  const screen = opened(
    [{source: "document-markdown", text: "# Doc", label: "Copy", fold: true}],
    {refuses: true});
  const payload = screen.at("document-markdown");
  assert.equal(payload.parentNode.open, false);
  await click(screen, "document-markdown");
  assert.equal(payload.parentNode.open, true);
});

test("a refusal unhides a payload that was hidden", async function () {
  const screen = opened(
    [{source: "document-text", text: "Doc", label: "Copy", hidden: true}],
    {refuses: true});
  assert.equal(screen.at("document-text").hidden, true);
  await click(screen, "document-text");
  assert.equal(screen.at("document-text").hidden, false);
});

test("a second click copies again and says so again", async function () {
  const screen = one();
  await click(screen, "post-text");
  screen.fire();
  assert.equal(screen.button("post-text").textContent, "Copy the post");
  await click(screen, "post-text");
  assert.deepEqual(screen.written, [POST, POST]);
  assert.equal(screen.button("post-text").textContent, "Copied");
});

test("a click while the label is still saying Copied restarts the wait",
     async function () {
  /* Otherwise the first timer fires mid way through the second copy and the
     button goes back to its label while the copy it is reporting is the one
     that just happened. */
  const screen = one();
  await click(screen, "post-text");
  await click(screen, "post-text");
  assert.equal(screen.button("post-text").textContent, "Copied");
  assert.equal(screen.pending().length, 1);
  screen.fire();
  assert.equal(screen.button("post-text").textContent, "Copy the post");
});

test("a refusal after a success does not get restored by the old timer",
     async function () {
  const screen = one();
  await click(screen, "post-text");
  screen.refuses = true;
  await click(screen, "post-text");
  assert.equal(screen.button("post-text").textContent, "Not copied");
  screen.fire();
  assert.equal(screen.button("post-text").textContent, "Not copied");
});

test("the click does not also submit whatever it sits in", function () {
  const screen = one();
  assert.equal(screen.button("post-text").dispatch("click"), true);
});
