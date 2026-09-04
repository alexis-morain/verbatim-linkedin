/* The interview screen's client.

   It posts one answer and reads the reply as it arrives. Server sent events
   over a POST rather than an EventSource, because EventSource speaks GET and
   a GET that spends somebody's API budget is reachable from any page they
   have open. web.py carries the reasoning.

   No user facing string is written in this file. They come from the language
   pack, through the JSON block the page renders, so a missing translation
   degrades exactly the way every other string does.

   Everything from the model or from a tool lands through textContent. It is
   untrusted text on its way to a screen, and innerHTML would make it markup. */

(function () {
  "use strict";

  var form = document.getElementById("say");
  var turns = document.getElementById("turns");
  var meter = document.getElementById("meter");
  var strings = document.getElementById("verbatim-strings");
  if (!turns || !strings) { return; }

  var T = JSON.parse(strings.textContent);
  /* What the form sends for "I read both and took neither". The same word
     the route reads, and a word rather than a number because every number
     in that field is an index into the lines. */
  var NONE_OF_THEM = "none";
  var box = form ? document.getElementById("text") : null;
  var button = form ? form.querySelector("button") : null;
  var ask = document.getElementById("ask-sheet");
  var write = document.getElementById("write-draft");
  var revision = document.getElementById("revision");
  var current = null;
  var channel = null;   /* where this turn's words go: see `into` below */
  var waiting = null;   /* the status line, for as long as the turn runs */
  var pending = null;   /* what was typed, until the turn is known to be real */
  var origin = null;    /* the box it was typed in, so the right one clears */
  var committed = false;  /* whether this turn's words reached disk */
  var landed = false;   /* whether this turn put a draft on the conversation */

  function fill(text, values) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, key) {
      return Object.prototype.hasOwnProperty.call(values, key)
        ? values[key] : whole;
    });
  }

  function trailing() {
    /* The status line says what is happening next, so it belongs after
       everything that has already happened. It is put up before the request
       leaves and the person's own words land later, on the frame that says
       they reached disk, so without this the screen reads as though the
       engine started working before they finished typing. */
    if (waiting && waiting.parentNode) {
      var host = waiting.parentNode;
      host.removeChild(waiting);
      host.appendChild(waiting);
    }
  }

  function into() {
    /* Where this turn's words belong. The interview thread for an interview
       turn, and the revision panel for a drafting one, because that is
       where the request was typed and where the scope, the echo of the
       passage and the box all are. A refusal shown at the top of the page
       while its own question sits further down is the defect this exists to
       refuse: answering it there means picking the passage again by hand. */
    return channel || turns;
  }

  function spoken(kind, label) {
    var wrap = document.createElement("div");
    wrap.className = "turn " + kind;
    var who = document.createElement("p");
    who.className = "who mono";
    who.textContent = label;
    var words = document.createElement("div");
    words.className = "words";
    wrap.appendChild(who);
    wrap.appendChild(words);
    into().appendChild(wrap);
    trailing();
    return words;
  }

  function note(text, failed) {
    var line = document.createElement("div");
    line.className = "turn tool mono" + (failed ? " tool-failed" : "");
    line.textContent = text;
    into().appendChild(line);
    trailing();
    return line;
  }

  function answered(frame) {
    var fold = document.createElement("details");
    fold.className = "turn tool";
    if (frame.is_error) { fold.open = true; }
    var head = document.createElement("summary");
    head.className = "mono";
    head.textContent = (frame.is_error ? T.tool_failed : T.tool_result)
      + " " + frame.name;
    var body = document.createElement("pre");
    body.className = "mono";
    body.textContent = frame.result;
    fold.appendChild(head);
    fold.appendChild(body);
    turns.appendChild(fold);
  }

  function phase(key) {
    /* What the turn is doing, on one line that lives as long as the turn.

       It used to be a single note removed the moment the response headers
       arrived, which is before the model has said anything: the gap it
       existed to cover was the one it was taken away for. Now it stays, and
       it says which phase, off what the server reports rather than off tool
       names read here: a client that knew the names would be a second place
       deciding which tool writes a post.

       A key the pack has no sentence for takes the line away rather than
       printing itself. That is the rule the stop reasons already follow: a
       bare token on a French screen is worse than no line at all.

       Removed and appended rather than left where it was, so it is the last
       thing in the channel. A status line above the words it is about reads
       as something that already happened. */
    var words = key ? T[key] : "";
    if (waiting) { waiting.remove(); waiting = null; }
    if (!words) { return; }
    waiting = note(words);
  }

  function handle(frame) {
    /* One frame says the words reached disk, and nothing else is guessed from.
       A refusal that arrives before it wrote nothing, so what was typed stays
       in the box; everything after it belongs to a turn that really happened,
       failures included. */
    if (frame.kind === "accepted") {
      /* This frame says the words are on disk, and nothing more. Whether the
         model still owes a reply is decided by the frame that ends the turn,
         or by the turn dying: hiding the affordance here would hide it for
         good on a stream that never gets to say anything else. */
      committed = true;
      gauge(frame);
      offerSheet();
      if (pending !== null) { commit(); }
      return;
    }
    if (frame.kind === "text") {
      /* Words are arriving, so the words are the signal. A line under them
         saying the model is thinking says something that is not true. */
      phase("");
      if (!current) { current = spoken("turn-asked", T.asked); }
      current.textContent += frame.text;
      return;
    }
    current = null;
    if (frame.kind === "sheet") {
      sheet(frame);
    } else if (frame.kind === "draft") {
      /* Noted, not painted. The panel is a server rendering, marks and
         verdicts included, and painting a second one here would be a second
         implementation of the thing this product is named after. The stream
         is left to finish, then the page is asked again. */
      landed = true;
      /* And that wait is real: the stream has to end before the page is
         asked again, and nothing else on the screen says why. */
      phase("waiting_finishing");
    } else if (frame.kind === "tool_call") {
      note(T.tool_call + " " + frame.name + " "
           + JSON.stringify(frame.arguments));
      if (frame.phase) { phase("waiting_" + frame.phase); }
    } else if (frame.kind === "tool_result") {
      answered(frame);
    } else if (frame.kind === "usage") {
      var line = fill(T.tokens, {input: frame.input_tokens,
                                 output: frame.output_tokens});
      if (frame.price !== null && frame.price !== undefined) {
        line += ", " + fill(T.spent, {amount: frame.price.toFixed(4)});
      }
      if (meter) { meter.textContent = line; }
    } else if (frame.kind === "stop") {
      owing(frame.owing);
      if (frame.stop !== "end_turn") {
        /* the engine maps an unrecognised reason to a bare token, and a bare
           token on a French screen is the language leak in miniature */
        note(T["stop_" + frame.stop] || fill(T.stop_unknown, {code: frame.stop}),
             true);
      }
    } else if (frame.kind === "ceiling") {
      owing(frame.owing);
      note(fill(T.ceiling, {count: frame.turns}), true);
    } else if (frame.kind === "error") {
      note(explain(frame.code, frame.technical), true);
      /* Only a turn that was accepted leaves the model owing a reply; a
         refusal decided before that wrote nothing to answer. */
      if (!frame.code || frame.code === "engine-failed") { owing(true); }
    }
  }

  function offerSheet() {
    /* The sheet is refused before anybody has said anything, because a sheet
       asked for then is a sheet the model has to invent. So the screen does
       not offer one until there is a turn on disk, and this is the frame
       that says there is. The page does not reload between two interview
       turns, so nothing else would put the button up until somebody
       reloaded and found out it had been there all along. */
    [ask, document.getElementById("ask-sheet-hint")].forEach(
      function (node) { if (node) { node.hidden = false; } });
  }

  function gauge(frame) {
    /* How much material is on the table, off the frame that says the words
       reached disk. It reads what the person said, so this is the moment it
       moves, and the server is the one that counts: a browser counting for
       itself would be a second implementation of the rule about which text
       credits, drifting from the one that matters.

       A frame carrying no counts leaves the line alone. Filling it from
       missing numbers would draw a gauge that fell to zero. */
    if (frame.ratio === undefined || frame.ratio === null) { return; }
    var ratio = document.getElementById("sufficiency-ratio");
    var counts = document.getElementById("sufficiency-counts");
    if (ratio) { ratio.textContent = fill(T.sufficiency, frame); }
    if (counts) {
      counts.textContent = fill(T.sufficiency_counts, frame);
    }
  }

  function refill(node, entries) {
    if (!node) { return; }
    while (node.firstChild) { node.removeChild(node.firstChild); }
    (entries || []).forEach(function (entry) {
      var item = document.createElement("li");
      item.textContent = entry;
      node.appendChild(item);
    });
  }

  function firstLines(entries) {
    /* The proposed openings, each one a choice rather than a line to read.
       The skill writes the post for the chosen proposal, to the character,
       and until somebody was asked nothing was ever chosen: a model with no
       decision opens on a lukewarm self description. So the step is on the
       screen, and the last option is refusing both, which is a decision and
       not the absence of one.

       Built here as well as in the template, because a sheet that lands
       mid stream fills this panel with no reload: a choice that only
       existed server side would be a step that disappears on the path
       everybody takes. The radios carry `form`, so they sit beside the line
       they are about and still travel with the approval below.

       Replaced whole, like every other list here. Radios left behind from
       an earlier proposal would offer lines this sheet does not have and
       carry indexes into it. */
    var list = document.getElementById("sheet-first-lines");
    if (!list) { return; }
    while (list.firstChild) { list.removeChild(list.firstChild); }
    (entries || []).forEach(function (entry, index) {
      list.appendChild(choice(String(index), entry));
    });
    if ((entries || []).length) {
      var neither = choice(NONE_OF_THEM, T.sheet_first_line_none);
      neither.className = "hint";
      list.appendChild(neither);
    }
  }

  function choice(value, label) {
    /* One radio and its words. `textContent` for the words, like every
       other thing on this page that came off a model. */
    var item = document.createElement("li");
    var wrap = document.createElement("label");
    var radio = document.createElement("input");
    radio.setAttribute("type", "radio");
    radio.setAttribute("name", "first_line");
    radio.setAttribute("value", value);
    radio.setAttribute("form", "sheet-approve");
    radio.setAttribute("required", "required");
    var words = document.createElement("span");
    words.textContent = label;
    wrap.appendChild(radio);
    wrap.appendChild(words);
    item.appendChild(wrap);
    return item;
  }

  function sheet(frame) {
    /* Values into slots, nothing else: the panel and its labels are on the
       page already, rendered from the language pack. The approve form is the
       page's own, a plain POST; nothing here writes an approval. */
    var panel = document.getElementById("sheet");
    if (!panel) { return; }
    var slots = {"sheet-angle": frame.angle, "sheet-moment": frame.moment,
                 "sheet-conviction": frame.conviction};
    Object.keys(slots).forEach(function (id) {
      var node = document.getElementById(id);
      if (node) { node.textContent = slots[id]; }
    });
    refill(document.getElementById("sheet-elements"), frame.elements);
    firstLines(frame.first_lines);
    /* How this sheet arrived, and it is not decoration. A sheet parsed out of
       an answer that ignored its tool is a weaker object than one a model
       committed to, and the person about to sign it decides with that in
       front of them. Revealed only when there is something to say, and
       re-hidden when a later proposal arrives clean. */
    var problems = frame.problems || [];
    refill(document.getElementById("sheet-problems"), problems);
    var block = document.getElementById("sheet-problems-block");
    if (block) { block.hidden = problems.length === 0; }
    /* The form signs what is displayed. Filling the panel without moving
       the digest would recreate, on the live path, exactly the stale
       signature the digest exists to refuse. */
    var digest = document.getElementById("sheet-digest");
    if (digest) { digest.value = frame.digest || ""; }
    var approve = document.getElementById("sheet-approve");
    if (approve) { approve.hidden = frame.state !== "proposed"; }
    panel.hidden = false;
  }

  function commit() {
    /* The words are on disk, so they come out of the box and into the thread.
       Which box is carried from the click rather than assumed: once the sheet
       is approved the answer box is not on the page at all, and the one that
       is holds a revision request. */
    spoken("turn-said", T.said).textContent = pending;
    if (origin) { origin.value = ""; }
    pending = null;
  }

  function explain(code, technical) {
    /* A refusal this app decided has a sentence in the pack. Anything else is
       a provider failing, and that keeps the lead-in saying so, followed by
       the provider's own words untouched. The technical half, an exception
       name or a provider message, is appended rather than dropped: it is the
       only thing that tells two identical sentences apart. */
    if (code) {
      var sentence = T["error_" + code.replace(/-/g, "_")]
        || (T.error_unknown + " " + code);
      return technical ? sentence + " " + technical : sentence;
    }
    return technical ? T.error + " " + technical : "";
  }

  function payloads(chunk) {
    chunk.split("\n").forEach(function (line) {
      if (line.lastIndexOf("data: ", 0) !== 0) { return; }
      var frame;
      try {
        frame = JSON.parse(line.slice(6));
      } catch (broken) {
        return;  /* half a frame at the tail: the next read completes it */
      }
      handle(frame);
    });
  }

  function drain(reader) {
    var decoder = new TextDecoder();
    var buffer = "";
    function pump(chunk) {
      if (chunk.done) {
        buffer += decoder.decode();  /* flush a split multibyte character */
        if (buffer.trim()) { payloads(buffer); }
        return;
      }
      buffer += decoder.decode(chunk.value, {stream: true});
      var parts = buffer.split("\n\n");
      buffer = parts.pop();
      parts.forEach(payloads);
      return reader.read().then(pump);
    }
    return reader.read().then(pump);
  }

  function send(text) {
    if (!text.trim()) { return; }
    run(text);
  }

  function busy(yes) {
    [box, button, again, ask, write, revision].forEach(function (node) {
      if (node) { node.disabled = yes; }
    });
  }

  function run(text) {
    /* An empty body is a resume: the words are already on disk and the model
       still owes a reply, so there is nothing to show and nothing to clear. */
    return stream(form.action, text, false, box);
  }

  function stream(url, text, reload, source, extra, panel) {
    /* One turn, whichever button started it. The three of them differ by
       where they post and by what the server does with it; a screen that
       carried three copies of this would grow three ways of failing. */
    busy(true);
    /* Emptied rather than appended to. What is in there is the last turn's
       exchange, and the request about to go answers it: two of them stacked
       reads as one conversation with itself, and the older half is the one
       nothing is about any more. */
    channel = panel || null;
    if (channel) {
      while (channel.firstChild) { channel.removeChild(channel.firstChild); }
      channel.hidden = false;
    }
    pending = text ? text : null;
    origin = source || null;
    committed = false;
    landed = false;
    current = null;   /* a cut answer must not swallow the next one */
    phase("thinking");
    return fetch(url, {
      method: "POST",
      headers: {"content-type": "application/x-www-form-urlencoded"},
      body: new URLSearchParams(
        Object.assign({text: text}, extra || {})).toString()
    }).then(function (reply) {
      if (!reply.ok) { phase(""); return refused(reply); }
      return drain(reply.body.getReader());
    }).catch(function (failure) {
      phase("");
      note(T.error + " " + failure, true);
      /* The stream died without saying why. If the words were written, the
         model still owes a reply and the screen has to keep saying so. */
      if (committed) { owing(true); }
    }).then(function () {
      pending = null;
      /* The turn is over, whatever it did. Nothing is waiting any more, and
         a line saying otherwise outlives the thing it describes. */
      if (!(reload && landed)) { phase(""); }
      if (reload && landed) {
        /* Asked again rather than patched: what came back is a whole panel,
           and the server is the one that decides what backs what. The reload
           happens at the end of the stream and never inside it, so nothing
           the person paid for is cut off mid turn. */
        location.reload();
        return;
      }
      busy(false);
      if (box) { box.focus(); }
    });
  }

  function refused(reply) {
    return reply.json().catch(function () { return {}; })
      .then(function (body) {
        note(explain(body.detail, "") || (T.error + " " + reply.status), true);
      });
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      send(box.value);
    });

    /* Sending from the keyboard, which is the gesture that keeps this
       feeling like being asked something rather than like filling a form.
       An addition, never a replacement: the submit button stays, because
       this page posts its forms with no JavaScript at all, and a form with
       no submit control is one a keyboard cannot send and a screen reader
       cannot announce. Both modifiers, since the machine under this is not
       always a Mac. */
    box.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        send(box.value);
      }
    });
  }

  var again = document.getElementById("resume");
  var awaiting = document.getElementById("awaiting");
  if (again) {
    again.addEventListener("click", function () {
      run("");
    });
  }

  if (ask) {
    /* The person decides the interview has enough material in it. The turn
       behind this requires the tool rather than asking for it, which is what
       makes the sheet happen on a model that would otherwise write about it. */
    ask.addEventListener("click", function () {
      stream(ask.getAttribute("data-url"), "", false, null);
    });
  }
  if (write) {
    /* An empty box is a plain rewrite, which the skill allows: a revision
       restarts from the interview material either way. What is typed is a
       request, and it is kept, which is why it travels with the turn rather
       than being cleared here and forgotten. */
    write.addEventListener("click", function () {
      stream(write.getAttribute("data-url"),
             revision ? revision.value : "", true, revision, aimedAt(),
             document.getElementById("revision-reply"));
    });
  }

  /* Which block this request is about, as the two fields the server needs:
     the index says which, and the digest says this page was not stale. Both
     are read at the click rather than kept in a variable, so a picker the
     person moved after typing is the one that counts. */
  var scope = document.getElementById("revision-scope");
  var echo = document.getElementById("revision-echo");
  var scopeLine = document.getElementById("revision-scope-line");

  function chosen() {
    if (!scope || !scope.value) { return null; }
    var option = scope.options[scope.selectedIndex];
    return option ? option : null;
  }

  function aimedAt() {
    var option = chosen();
    return option
      ? {passage: option.getAttribute("data-digest"),
         passage_index: scope.value}
      : {};
  }

  if (scope) {
    scope.addEventListener("change", function () {
      var option = chosen();
      /* The exact text, through textContent: a post is somebody's prose and
         it reaches this page as prose, never as markup. */
      if (echo) {
        echo.textContent = option ? option.getAttribute("data-text") : "";
        echo.hidden = !option;
      }
      if (scopeLine) { scopeLine.hidden = !option; }
    });
  }

  function owing(yes) {
    /* Whether the model still owes a reply. The server decided it when the
       page was built; a turn that lands, or fails, changes it, and an
       affordance that lies about it is worse than none. */
    [again, awaiting].forEach(function (node) {
      if (node) { node.hidden = !yes; }
    });
  }

  Array.prototype.forEach.call(
    document.querySelectorAll(".seed"), function (seed) {
      seed.addEventListener("click", function () {
        if (!box) { return; }
        box.value = seed.getAttribute("data-text");
        box.focus();
      });
    });
}());
