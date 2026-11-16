// Selfbrowse site v2: theme switch, copy buttons, and "read this page" mode. No tracking, no network calls.
(function () {
  var root = document.documentElement;

  // Theme: remembered per viewer when storage is available.
  function stored() { try { return localStorage.getItem("sb-theme"); } catch (e) { return null; } }
  function store(v) { try { localStorage.setItem("sb-theme", v); } catch (e) {} }
  var saved = stored();
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  function current() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  var themeBtn = document.getElementById("theme");
  function labelTheme() { themeBtn.setAttribute("aria-label", current() === "dark" ? "Switch to light theme" : "Switch to dark theme"); }
  labelTheme();
  themeBtn.addEventListener("click", function () {
    var next = current() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next); store(next); labelTheme();
  });

  // Copy buttons.
  document.querySelectorAll(".copy").forEach(function (b) {
    b.addEventListener("click", function () {
      var text = document.getElementById(b.getAttribute("data-copy")).innerText;
      var ok = function () { b.textContent = "Copied"; b.classList.add("done"); setTimeout(function () { b.textContent = "Copy"; b.classList.remove("done"); }, 1600); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, function () { b.textContent = "Select and copy"; });
      else b.textContent = "Select and copy";
    });
  });

  // Read this page the way the model does.
  var toggle = document.getElementById("read-toggle");
  var reader = document.getElementById("reader");
  var list = document.getElementById("reader-list");
  var call = document.getElementById("reader-call");
  var closeBtn = document.getElementById("reader-close");
  var tagged = [];

  function visible(el) { return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length); }
  function name(el) {
    var n = el.getAttribute("aria-label") || el.innerText || el.textContent || "";
    return n.replace(/\s+/g, " ").trim().slice(0, 70);
  }
  function role(el) {
    var t = el.tagName.toLowerCase();
    if (t === "a") return "link";
    if (t === "button") return "button";
    return "heading";
  }
  function line(n, el) {
    var r = role(el), text = '<span class="r">#' + n + "</span>" + r + ' "' + esc(name(el)) + '"';
    if (r === "link") {
      var href = el.getAttribute("href") || "";
      if (href.indexOf("http") === 0) { try { var u = new URL(href); href = u.host + u.pathname.replace(/\/$/, ""); } catch (e) {} }
      text += " (→" + esc(href) + ")";
    }
    return text;
  }
  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function build() {
    tagged = [];
    list.innerHTML = "";
    var meta = document.createElement("li");
    meta.className = "meta";
    meta.textContent = "['" + document.title + "' | " + location.href.split("#")[0] + "]";
    list.appendChild(meta);
    var els = document.querySelectorAll("header a, header button, main a, main button, main h1, main h2, footer a");
    var n = 0;
    els.forEach(function (el) {
      if (!visible(el) || el.closest(".reader") || el.classList.contains("skip")) return;
      n += 1;
      el.setAttribute("data-sbref", n);
      tagged.push(el);
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.innerHTML = line(n, el);
      (function (num, target) {
        b.addEventListener("click", function () {
          call.textContent = (role(target) === "heading" ? "scroll" : "click") + ' {"ref": ' + num + "}";
          target.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
          target.classList.remove("flash"); void target.offsetWidth; target.classList.add("flash");
        });
      })(n, el);
      li.appendChild(b);
      list.appendChild(li);
    });
    call.textContent = "…";
  }
  function clear() { tagged.forEach(function (el) { el.removeAttribute("data-sbref"); el.classList.remove("flash"); }); tagged = []; }

  function open() { toggle.lastChild.textContent = "Stop reading this page"; toggle.setAttribute("aria-expanded", "true"); reader.hidden = false; build(); closeBtn.focus(); }
  function close() { reader.hidden = true; clear(); toggle.setAttribute("aria-expanded", "false"); toggle.lastChild.textContent = "Read this page the way the model does"; toggle.focus(); }
  toggle.addEventListener("click", function () { reader.hidden ? open() : close(); });
  closeBtn.addEventListener("click", close);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !reader.hidden) close(); });
})();
