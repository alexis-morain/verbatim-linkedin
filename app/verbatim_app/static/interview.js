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
  var box = form ? document.getElementById("text") : null;
  var button = form ? form.querySelector("button") : null;
  var current = null;
  var pending = null;   /* what was typed, until the turn is known to be real */
  var committed = false;  /* whether this turn's words reached disk */

  function fill(text, values) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, key) {
      return Object.prototype.hasOwnProperty.call(values, key)
        ? values[key] : whole;
    });
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
    turns.appendChild(wrap);
    return words;
  }

  function note(text, failed) {
    var line = document.createElement("div");
    line.className = "turn tool mono" + (failed ? " tool-failed" : "");
    line.textContent = text;
    turns.appendChild(line);
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
      if (pending !== null) { commit(); }
      return;
    }
    if (frame.kind === "text") {
      if (!current) { current = spoken("turn-asked", T.asked); }
      current.textContent += frame.text;
      return;
    }
    current = null;
    if (frame.kind === "tool_call") {
      note(T.tool_call + " " + frame.name + " "
           + JSON.stringify(frame.arguments));
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

  function commit() {
    spoken("turn-said", T.said).textContent = pending;
    box.value = "";
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

  function run(text) {
    /* An empty body is a resume: the words are already on disk and the model
       still owes a reply, so there is nothing to show and nothing to clear. */
    box.disabled = true;
    button.disabled = true;
    if (again) { again.disabled = true; }
    pending = text ? text : null;
    committed = false;
    current = null;   /* a cut answer must not swallow the next one */
    var waiting = note(T.thinking);
    fetch(form.action, {
      method: "POST",
      headers: {"content-type": "application/x-www-form-urlencoded"},
      body: new URLSearchParams({text: text}).toString()
    }).then(function (reply) {
      waiting.remove();
      if (!reply.ok) { return refused(reply); }
      return drain(reply.body.getReader());
    }).catch(function (failure) {
      waiting.remove();
      note(T.error + " " + failure, true);
      /* The stream died without saying why. If the words were written, the
         model still owes a reply and the screen has to keep saying so. */
      if (committed) { owing(true); }
    }).then(function () {
      pending = null;
      box.disabled = false;
      button.disabled = false;
      if (again) { again.disabled = false; }
      box.focus();
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
  }

  var again = document.getElementById("resume");
  var awaiting = document.getElementById("awaiting");
  if (again) {
    again.addEventListener("click", function () {
      run("");
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
