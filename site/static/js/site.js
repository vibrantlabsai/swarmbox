/* swarmbox site.js: old-anchor redirects, theme toggle, copy buttons, docs
   menu, the hero's animation, waitlist modal. No dependencies. */
(function () {
  var root = document.documentElement;

  // The site was one page until the docs moved to pages of their own. Links
  // to its sections are still out there (the PyPI page has one), so on the
  // home page an old anchor goes to the page that section became.
  var moved = {
    'install-the-tools': '/docs/quickstart/#install-the-tools',
    'point-it-at-the-test-bed': '/docs/quickstart/#point-it-at-the-test-bed',
    'get-the-tasks': '/docs/quickstart/#get-the-tasks',
    'run-16-rollouts-at-once': '/docs/quickstart/#run-16-rollouts-at-once',
    'check-the-results': '/docs/quickstart/#check-the-results',
    'know-the-limits': '/docs/limits/',
    'if-you-used-opendsec': '/docs/migrate-from-opendsec/',
    'if-something-fails': '/docs/troubleshooting/'
  };
  var to = location.pathname === '/' && moved[location.hash.slice(1)];
  if (to) { location.replace(to); return; }

  // Theme
  document.addEventListener('click', function (ev) {
    var t = ev.target.closest('[data-theme-toggle]');
    if (!t) return;
    var dark = root.classList.toggle('dark');
    try { localStorage.setItem('sb-theme', dark ? 'dark' : 'light'); } catch (e) {}
    document.dispatchEvent(new Event('sb-theme'));
  });

  // Copy buttons
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('.copy');
    if (!b) return;
    var box = b.closest('[data-copy]');
    var src = box && box.querySelector('[data-src]');
    if (!src || !navigator.clipboard) return;
    navigator.clipboard.writeText(src.innerText.replace(/\n$/, '')).then(function () {
      b.setAttribute('data-ok', '');
      setTimeout(function () { b.removeAttribute('data-ok'); }, 1400);
    }).catch(function () {});
  });

  // Docs menu on phones
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('.side-t');
    if (!b) return;
    var open = b.closest('[data-side]').classList.toggle('open');
    b.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  // The hero's Worlds animate only while they are on screen.
  var worlds = document.querySelector('.worlds');
  if (worlds && 'IntersectionObserver' in window) {
    new IntersectionObserver(function (es) {
      worlds.classList.toggle('paused', !es[es.length - 1].isIntersecting);
    }).observe(worlds);
  }

  // Waitlist modal
  var scrim = document.getElementById('waitlist');
  if (!scrim) return;
  var form = scrim.querySelector('form');
  var fieldset = form.querySelector('fieldset');
  var alertBox = scrim.querySelector('[data-alert]');
  var wrap = scrim.querySelector('[data-form-wrap]');
  var done = scrim.querySelector('[data-done]');
  var submit = form.querySelector('[type=submit]');
  var spin = submit.querySelector('.spin');
  var label = submit.querySelector('[data-label]');
  // The endpoint accepts exactly these fields, and for the last three
  // exactly the values in layouts/partials/modal.html.
  var keys = ['name', 'email', 'company', 'role', 'workload', 'peak_sandboxes', 'task_format'];
  var names = { name: 'name', email: 'email address', company: 'company', role: 'role',
    workload: 'workload', peak_sandboxes: 'peak concurrent Sandboxes', task_format: 'task format' };
  var failed = 'Something went wrong on our side. Please try again in a few minutes.';
  var lastFocus = null;

  function open() {
    if (!scrim.hidden) return;
    lastFocus = document.activeElement;
    scrim.hidden = false;
    root.classList.add('lock');
    var first = scrim.querySelector('input');
    if (first && !wrap.hidden) first.focus();
  }
  function close() {
    scrim.hidden = true;
    root.classList.remove('lock');
    if (done.hidden === false) { done.hidden = true; wrap.hidden = false; form.reset(); }
    // Drop #waitlist from the address, so a later link to it opens the form again.
    if (location.hash === '#waitlist' && history.replaceState) history.replaceState(null, '', location.pathname + location.search);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function showAlert(msg) { alertBox.textContent = msg; alertBox.hidden = !msg; }
  function mark(k, bad) {
    var input = form.querySelector('#f-' + k);
    var group = form.querySelector('[data-group="' + k + '"]');
    var el = input || group;
    el.classList.toggle('bad', bad);
    el.setAttribute('aria-invalid', bad ? 'true' : 'false');
    form.querySelector('#e-' + k).hidden = !bad;
  }
  function focusField(k) {
    var el = form.querySelector('#f-' + k) || form.querySelector('[name="' + k + '"]');
    if (el) el.focus();
  }
  function sending(on) {
    fieldset.disabled = on;
    spin.hidden = !on;
    label.textContent = on ? 'Sending' : 'Join the waitlist';
  }
  // A refused entry (400) says why, as {"error": "<field> is ..."}: mark
  // that field and say it in a sentence.
  function refused(msg) {
    var m = /^([a-z_]+) is (required|not valid|not one of the choices)$/.exec(msg || '');
    if (!m || !names[m[1]]) { showAlert('We could not accept that entry. Check each field and try again.'); return; }
    mark(m[1], true);
    showAlert(m[2] === 'not valid'
      ? 'We could not accept the ' + names[m[1]] + ' as written. Use plain text of up to 200 characters that starts with a letter or a digit.'
      : 'Fill in the ' + names[m[1]] + '.');
    focusField(m[1]);
  }

  // Any link to #waitlist opens the form, on whatever page it points at:
  // every page carries the form.
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest('a[href$="#waitlist"]');
    if (a) { ev.preventDefault(); open(); return; }
    if (ev.target.closest('[data-close]') || ev.target === scrim) close();
  });
  document.addEventListener('keydown', function (ev) {
    if (scrim.hidden) return;
    if (ev.key === 'Escape') { close(); return; }
    if (ev.key !== 'Tab') return;
    var f = scrim.querySelectorAll('button:not([disabled]):not([hidden]), input:not([disabled]):not([tabindex="-1"]), a[href]');
    f = Array.prototype.filter.call(f, function (el) { return el.offsetParent !== null; });
    if (!f.length) { ev.preventDefault(); return; }
    var first = f[0], last = f[f.length - 1], at = document.activeElement;
    // Focus that is not on one of these (the form is disabled while it
    // sends) goes back into the modal, never to the page behind it.
    if (f.indexOf(at) < 0) { ev.preventDefault(); (ev.shiftKey ? last : first).focus(); }
    else if (ev.shiftKey && at === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && at === last) { ev.preventDefault(); first.focus(); }
  });
  window.addEventListener('hashchange', function () { if (location.hash === '#waitlist') open(); });
  if (location.hash === '#waitlist') open();

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var fd = new FormData(form);
    var data = {}, missing = [];
    keys.forEach(function (k) {
      var v = String(fd.get(k) || '').trim();
      var bad = !v || (k === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v));
      mark(k, bad);
      if (bad) missing.push(k); else data[k] = v;
    });
    if (missing.length) {
      showAlert(missing.length === 1 ? '1 field needs attention.' : missing.length + ' fields need attention.');
      focusField(missing[0]);
      return;
    }
    // The hidden field: people leave it empty, and the endpoint drops an entry that fills it.
    var trap = String(fd.get('website') || '');
    if (trap) data.website = trap;
    var endpoint = form.getAttribute('data-endpoint');
    if (!endpoint) { showAlert('The waitlist is not open yet. Please check back soon.'); return; }
    showAlert('');
    sending(true);
    var ctl = 'AbortController' in window ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 20000);
    fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal: ctl ? ctl.signal : undefined })
      .then(function (r) {
        clearTimeout(timer);
        if (r.ok) { sending(false); wrap.hidden = true; done.hidden = false; done.querySelector('[data-close]').focus(); return; }
        if (r.status !== 400) { sending(false); showAlert(failed); return; }
        return r.json().catch(function () { return null; }).then(function (b) { sending(false); refused(b && b.error); });
      })
      .catch(function (err) {
        // No answer at all: offline, blocked, or the 20 seconds ran out.
        clearTimeout(timer);
        sending(false);
        showAlert(err && err.name === 'AbortError'
          ? 'That took too long, and we stopped waiting. Please try again.'
          : 'We could not reach the waitlist. Check your connection and try again.');
      });
  });
})();
