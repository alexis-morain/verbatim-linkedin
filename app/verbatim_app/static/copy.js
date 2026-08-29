/* Copy buttons.

   Every button on these screens is made here and none of them is in the
   HTML. Two reasons, and both are rules this app already keeps. A button
   rendered by the server would be a dead button on a browser with no script,
   and every screen but the interview works without one. And a browser with
   no clipboard at all, which is what a page served over anything but
   loopback or https gets, would have a button that cannot work: below, no
   clipboard means no button, and the text is still there to select.

   **What is copied is what the server wrote, never what is on the screen.**
   Each button names an element by id and copies its text. Reading the
   rendered document instead would recompose markdown out of HTML, which is
   copying an approximation of somebody's own file; on a post it would be
   worse than an approximation, because the element holding the post is the
   only one that has had the session notes cut off it.

   **A refusal says so and stays saying so.** writeText rejects when the
   document is not focused or permission is denied, and a button that then
   went back to reading "Copy" would be claiming a copy that never happened.
   The success word times out, the failure word does not, the sentence
   explaining it appears beside the button rather than inside it, and the
   text is unfolded so it can be selected by hand.
*/

"use strict";

(function () {
  var clipboard = navigator.clipboard;
  if (!clipboard || !clipboard.writeText) { return; }

  /* Show the text a button copies, for the case where the copy failed and
     the person has to do it by hand. Three shapes and one rule: a corpus
     file keeps its bytes behind a fold, the plain text of a document is
     hidden outright, and a post is already on the screen, where this does
     nothing. */
  function reveal(source) {
    source.hidden = false;
    var parent = source.parentNode;
    // A browser reports tagName upper case for HTML elements, the test DOM
    // reports what the template wrote. Neither is worth depending on.
    if (parent && String(parent.tagName).toLowerCase() === "details") {
      parent.open = true;
    }
  }

  function wire(slot) {
    var source = document.getElementById(slot.getAttribute("data-source"));
    if (!source) { return; }

    var label = slot.getAttribute("data-label");
    var done = slot.getAttribute("data-done");
    var failed = slot.getAttribute("data-failed");
    var why = slot.getAttribute("data-failed-hint");

    var button = document.createElement("button");
    button.setAttribute("type", "button");
    button.className = "copy-button";
    button.textContent = label;

    /* The word goes in the button and the sentence goes beside it. A
       paragraph written into a button's own text is a button the width of a
       paragraph, and the failure is exactly the moment somebody needs both:
       a label that fits and an explanation that says what to do instead. */
    var said = document.createElement("span");
    said.className = "copy-said";
    said.setAttribute("role", "status");
    said.hidden = true;

    var timer = null;
    button.addEventListener("click", function (event) {
      if (event && event.preventDefault) { event.preventDefault(); }
      if (timer !== null) { clearTimeout(timer); timer = null; }
      clipboard.writeText(source.textContent).then(function () {
        button.textContent = done;
        said.hidden = true;
        timer = setTimeout(function () {
          timer = null;
          button.textContent = label;
        }, 2000);
      }, function () {
        button.textContent = failed;
        // Shown before it is written: a live region that changes while it is
        // still hidden is a change some readers never announce.
        said.hidden = false;
        said.textContent = why;
        reveal(source);
      });
    });

    slot.appendChild(button);
    slot.appendChild(said);
  }

  var slots = document.querySelectorAll(".copy-slot");
  for (var i = 0; i < slots.length; i += 1) { wire(slots[i]); }
})();
