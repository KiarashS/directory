/* ==========================================================================
   directory.kiarashs.ir — tabs, search, view mode, theme.

   Every entry is already in the HTML when this file runs, so all of this is
   enhancement: without it the page is five stacked sections that still work.
   ========================================================================== */

(function () {
  'use strict';

  var root = document.documentElement;
  root.classList.replace('no-js', 'js');

  /* --- Theme ------------------------------------------------------------
     Three states, cycled by the header button: system → light → dark.
     "system" is the absence of data-theme, so the CSS media query decides. */

  var THEME_KEY = 'directory:theme';
  var THEME_ORDER = ['system', 'light', 'dark'];
  var themeBtn = document.querySelector('[data-theme-toggle]');

  function store(key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) { /* private mode, or site data blocked */ }
  }

  function read(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function currentTheme() {
    return root.getAttribute('data-theme') || 'system';
  }

  function applyTheme(theme) {
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    store(THEME_KEY, theme === 'system' ? null : theme);

    if (themeBtn) {
      var next = THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length];
      themeBtn.setAttribute('aria-label', 'Theme: ' + theme + '. Switch to ' + next + '.');
      themeBtn.setAttribute('title', 'Theme: ' + theme);
    }

    // Keep the browser chrome in step with the page.
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      var dark = theme === 'dark' || (theme === 'system' &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);
      meta.setAttribute('content', dark ? '#0a0c11' : '#f4f5f8');
    }
  }

  applyTheme(currentTheme());

  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var i = THEME_ORDER.indexOf(currentTheme());
      applyTheme(THEME_ORDER[(i + 1) % THEME_ORDER.length]);
    });
  }

  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
    if (currentTheme() === 'system') applyTheme('system');
  });

  /* --- Elements ---------------------------------------------------------- */

  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('[role="tabpanel"]'));
  // Cards and the course disclosures both carry data-search, so both filter.
  var entries = Array.prototype.slice.call(document.querySelectorAll('[data-search]'));
  var cards = entries.filter(function (el) { return el.classList.contains('card'); });
  var input = document.getElementById('search');
  var empty = document.querySelector('.empty');
  var emptyTerm = document.querySelector('[data-empty-term]');
  var liveRegion = document.querySelector('[data-live]');
  var viewButtons = Array.prototype.slice.call(document.querySelectorAll('[data-view]'));
  var toTop = document.querySelector('.to-top');

  var tablist = document.querySelector('[role="tablist"]');
  var resultsBar = document.querySelector('.results-bar');
  var resultsText = document.querySelector('[data-results-text]');

  // Cache the haystack once; reading a data attribute 373 times per keystroke
  // is the only thing here that could ever get slow.
  var haystack = new Map();
  entries.forEach(function (el) {
    haystack.set(el, (el.getAttribute('data-search') || '').toLowerCase());
  });

  /* --- Tabs -------------------------------------------------------------- */

  var slugs = tabs.map(function (t) { return t.getAttribute('data-slug'); });
  var active = slugs[0];

  function selectTab(slug, opts) {
    if (slugs.indexOf(slug) === -1) slug = slugs[0];
    active = slug;

    tabs.forEach(function (tab) {
      var on = tab.getAttribute('data-slug') === slug;
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.tabIndex = on ? 0 : -1;
    });

    render();

    if (opts && opts.focus) {
      var el = tabs[slugs.indexOf(slug)];
      el.focus();
      el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
    if (!opts || opts.hash !== false) {
      if (('#' + slug) !== window.location.hash) {
        history.replaceState(null, '', '#' + slug);
      }
    }
  }

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      selectTab(tab.getAttribute('data-slug'));
    });
  });

  tablist.addEventListener('keydown', function (e) {
    var i = slugs.indexOf(active);
    var next = null;
    if (e.key === 'ArrowRight') next = (i + 1) % slugs.length;
    else if (e.key === 'ArrowLeft') next = (i - 1 + slugs.length) % slugs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = slugs.length - 1;
    if (next === null) return;
    e.preventDefault();
    selectTab(slugs[next], { focus: true });
  });

  window.addEventListener('hashchange', function () {
    var slug = window.location.hash.replace('#', '').toLowerCase();
    if (slug && slug !== active && slugs.indexOf(slug) !== -1) {
      selectTab(slug, { hash: false });
    }
  });

  /* --- Search ------------------------------------------------------------ */

  var query = '';

  function render() {
    var q = query.trim().toLowerCase();
    var terms = q ? q.split(/\s+/) : [];
    var searching = terms.length > 0;
    var total = 0;
    var hitCategories = 0;

    panels.forEach(function (panel) {
      var slug = panel.getAttribute('data-slug');
      var shown = 0;

      Array.prototype.forEach.call(panel.querySelectorAll('[data-search]'), function (el) {
        var text = haystack.get(el) || '';
        var hit = !searching || terms.every(function (t) { return text.indexOf(t) !== -1; });
        el.hidden = !hit;
        if (hit) shown++;
      });

      // While searching, every panel holding a hit is on screen at once;
      // otherwise only the selected tab's panel shows.
      panel.hidden = searching ? shown === 0 : slug !== active;
      if (searching) panel.setAttribute('data-searching', '');
      else panel.removeAttribute('data-searching');

      var count = panel.querySelector('[data-panel-count]');
      if (count) count.textContent = shown + (shown === 1 ? ' entry' : ' entries');

      var tab = tabs[slugs.indexOf(slug)];
      if (tab) {
        var badge = tab.querySelector('.tab-count');
        if (badge) badge.textContent = searching ? shown : badge.getAttribute('data-total');
        tab.toggleAttribute('data-empty', searching && shown === 0);
      }

      total += shown;
      if (shown > 0) hitCategories++;
    });

    tablist.toggleAttribute('data-searching', searching);
    document.body.classList.toggle('is-searching', searching);

    if (empty) empty.toggleAttribute('data-visible', searching && total === 0);
    if (emptyTerm) emptyTerm.textContent = query.trim();

    var summary = total + (total === 1 ? ' result' : ' results') +
      ' for \u201c' + query.trim() + '\u201d' +
      (hitCategories > 1 ? ' in ' + hitCategories + ' categories' : '');

    if (resultsBar) resultsBar.toggleAttribute('data-visible', searching && total > 0);
    if (resultsText) resultsText.textContent = summary;
    if (liveRegion) liveRegion.textContent = searching ? summary : '';
  }

  function setQuery(value) {
    query = value;
    render();
  }

  if (input) {
    var pending;
    input.addEventListener('input', function () {
      // 371 cards is small enough to filter synchronously, but a frame of
      // debounce keeps typing smooth on low-end phones.
      cancelAnimationFrame(pending);
      pending = requestAnimationFrame(function () { setQuery(input.value); });
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && input.value) {
        e.preventDefault();
        input.value = '';
        setQuery('');
      }
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-search-clear]'), function (btn) {
    btn.addEventListener('click', function () {
      input.value = '';
      setQuery('');
      input.focus();
    });
  });

  document.addEventListener('keydown', function (e) {
    if (!input) return;
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) ||
      document.activeElement.isContentEditable;

    var slash = e.key === '/' && !typing && !e.metaKey && !e.ctrlKey && !e.altKey;
    var cmdK = (e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey);

    if (slash || cmdK) {
      e.preventDefault();
      input.focus();
      input.select();
    }
  });

  /* --- View mode --------------------------------------------------------- */

  var VIEW_KEY = 'directory:view';

  function applyView(view) {
    if (view !== 'list') view = 'grid';
    document.body.classList.toggle('view-list', view === 'list');
    viewButtons.forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-view') === view ? 'true' : 'false');
    });
    store(VIEW_KEY, view);
  }

  viewButtons.forEach(function (btn) {
    btn.addEventListener('click', function () { applyView(btn.getAttribute('data-view')); });
  });
  applyView(read(VIEW_KEY) || 'grid');

  /* --- Back to top ------------------------------------------------------- */

  if (toTop) {
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      if (input) input.blur();
    });
    var ticking = false;
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        toTop.toggleAttribute('data-visible', window.scrollY > 700);
        ticking = false;
      });
    }, { passive: true });
  }

  /* --- Deep links -------------------------------------------------------- */

  // #pdfs, #links, … pick the tab. ?h=<link text> still flags one entry and
  // scrolls to it, the way the old page did.
  var hash = window.location.hash.replace('#', '').toLowerCase();
  selectTab(slugs.indexOf(hash) !== -1 ? hash : slugs[0], { hash: !!hash });

  var flag = new URLSearchParams(window.location.search).get('h');
  if (flag) {
    var wanted = flag.trim().toLowerCase();
    var match = cards.filter(function (card) {
      var t = card.querySelector('.card-title');
      return t && t.textContent.trim().toLowerCase() === wanted;
    })[0];

    if (match) {
      var panel = match.closest('[role="tabpanel"]');
      if (panel) selectTab(panel.getAttribute('data-slug'), { hash: false });
      match.classList.add('is-flagged');
      requestAnimationFrame(function () {
        match.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }
  }
})();
