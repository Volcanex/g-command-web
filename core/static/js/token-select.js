/* ============================================================
   token-select.js
   Pre-wraps text into .tok-N spans so native selection renders
   the LLM-token look (see tokens/selection.css). One span per
   word; words longer than 5 chars split into 4-char chunks.
   Colours cycle through the palette across the whole document
   so a selection spanning many words reads as varied tokens.

   Whitespace is preserved as bare text nodes (line-wrapping is
   unaffected). Skips script/style/inputs and name wordmarks
   (.g-name) so their treatment is untouched. Idempotent.

   Scope: tags [data-tokens] if present, else <body>.
   Static surfaces only: React views re-render away the spans.
   ============================================================ */
(function () {
  var COUNT = 6;
  var SKIP_TAG = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEXTAREA: 1, INPUT: 1, SELECT: 1, CODE: 1, KBD: 1, SAMP: 1, SVG: 1 };
  var n = 0;

  function tok(str) {
    var s = document.createElement("span");
    s.className = "tok-" + (n++ % COUNT);
    s.textContent = str;
    return s;
  }

  function wrap(node) {
    var text = node.nodeValue;
    if (!text || !/\S/.test(text)) return;            // keep whitespace-only as-is
    var frag = document.createDocumentFragment();
    var parts = text.split(/(\s+)/);                   // keep the separators
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i];
      if (part === "") continue;
      if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(part)); continue; }
      if (part.length > 5) {
        for (var j = 0; j < part.length; j += 4) frag.appendChild(tok(part.slice(j, j + 4)));
      } else {
        frag.appendChild(tok(part));
      }
    }
    node.parentNode.replaceChild(frag, node);
  }

  function walk(el) {
    if (!el) return;
    if (el.tagName && SKIP_TAG[el.tagName]) return;
    if (el.nodeType === 1) {
      if (el.getAttribute("data-no-tokens") !== null) return;
      var cl = el.classList;
      if (cl && (cl.contains("g-name") || cl.contains("tok-0") || cl.contains("tok-1") ||
                 cl.contains("tok-2") || cl.contains("tok-3") || cl.contains("tok-4") || cl.contains("tok-5"))) return;
      if (el.getAttribute("data-tok-done")) return;
    }
    var kids = Array.prototype.slice.call(el.childNodes);
    for (var i = 0; i < kids.length; i++) {
      var k = kids[i];
      if (k.nodeType === 3) wrap(k);
      else if (k.nodeType === 1) walk(k);
    }
    if (el.nodeType === 1) el.setAttribute("data-tok-done", "1");
  }

  function run() {
    walk(document.querySelector("[data-tokens]") || document.body);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
})();
