/* ==========================================================================
   directory.kiarashs.ir — tabs, search, view mode, theme.

   Every entry is already in the HTML when this file runs, so all of this is
   enhancement: without it the page is five stacked sections that still work.
   ========================================================================== */

(function () {
  'use strict';

  // The inline script in <head> already swapped no-js for js, before first
  // paint, so the inline link lists never flash into view.
  var root = document.documentElement;

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

  var tabs = Array.prototype.slice.call(document.querySelectorAll('nav.tabs .tab'));
  // Cards and the course disclosures both carry data-search, so both filter.
  var entries = Array.prototype.slice.call(document.querySelectorAll('[data-search]'));
  var cards = entries.filter(function (el) { return el.classList.contains('card'); });
  var input = document.getElementById('search');
  var empty = document.querySelector('.empty');
  var emptyTerm = document.querySelector('[data-empty-term]');
  var liveRegion = document.querySelector('[data-live]');
  var viewButtons = Array.prototype.slice.call(document.querySelectorAll('[data-view]'));
  var toTop = document.querySelector('.to-top');

  var main = document.getElementById('main');
  var base = (main && main.dataset.base) || './';
  var navBar = document.querySelector('nav.tabs');
  var elsewhere = document.querySelector('.elsewhere');
  var elsewhereList = document.querySelector('[data-elsewhere]');
  var resultsBar = document.querySelector('.results-bar');
  var resultsText = document.querySelector('[data-results-text]');

  // Cache the haystack once; reading a data attribute 373 times per keystroke
  // is the only thing here that could ever get slow.
  var haystack = new Map();
  entries.forEach(function (el) {
    haystack.set(el, (el.getAttribute('data-search') || '').toLowerCase());
  });

  /* --- Search ------------------------------------------------------------ */

  var query = '';

  // Every entry on the site as [title, category-slug]. Inlined on each page so
  // a search from /pdfs/ can still turn up something filed under /datasets/
  // without that page carrying another page's markup.
  var siteIndex = [];
  try {
    var raw = document.getElementById('search-index');
    if (raw) siteIndex = JSON.parse(raw.textContent);
  } catch (err) { /* a missing index just means search stays local */ }

  // Which category this page is showing. The front page lists the PDF entries,
  // so its nav marks PDFs current and this resolves to "pdfs" there too —
  // without that, all 139 of them would show up again as "found elsewhere".
  var current = document.querySelector('nav.tabs .tab[aria-current="page"]');
  var here = current ? current.getAttribute('data-slug') : '';

  function render() {
    var q = query.trim().toLowerCase();
    var terms = q ? q.split(/\s+/) : [];
    var searching = terms.length > 0;
    var shown = 0;

    entries.forEach(function (el) {
      var text = haystack.get(el) || '';
      var hit = !searching || terms.every(function (t) { return text.indexOf(t) !== -1; });
      el.hidden = !hit;
      if (hit) shown++;
    });

    // Matches that live on another page become links across to it. ?h= is the
    // deep link this script already understands: it flags the entry and
    // scrolls to it on arrival.
    var away = [];
    if (searching) {
      siteIndex.forEach(function (row) {
        if (row[1] === here) return;
        var text = (row[0] + ' ' + row[1]).toLowerCase();
        if (terms.every(function (t) { return text.indexOf(t) !== -1; })) away.push(row);
      });
    }

    if (elsewhereList) {
      elsewhereList.replaceChildren();
      away.slice(0, 40).forEach(function (row) {
        var li = document.createElement('li');
        li.className = 'card';
        var a = document.createElement('a');
        a.className = 'card-title';
        a.href = base + row[1] + '/?h=' + encodeURIComponent(row[0]);
        a.textContent = row[0];                       // textContent, never innerHTML
        var foot = document.createElement('div');
        foot.className = 'card-foot';
        var badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = row[1];
        foot.appendChild(badge);
        li.appendChild(a);
        li.appendChild(foot);
        elsewhereList.appendChild(li);
      });
      elsewhere.hidden = away.length === 0;
    }

    document.body.classList.toggle('is-searching', searching);
    if (navBar) navBar.toggleAttribute('data-searching', searching);

    var total = shown + away.length;
    if (empty) empty.toggleAttribute('data-visible', searching && total === 0);
    if (emptyTerm) emptyTerm.textContent = query.trim();

    var summary = total + (total === 1 ? ' result' : ' results') +
      ' for \u201c' + query.trim() + '\u201d' +
      (away.length ? ' (' + away.length + ' in other sections)' : '');

    if (resultsBar) resultsBar.toggleAttribute('data-visible', searching && total > 0);
    if (resultsText) resultsText.textContent = summary;
    if (liveRegion) liveRegion.textContent = searching ? summary : '';
  }

  // Writing the address bar on every keystroke would be wasteful and would
  // make the URL flicker, so the filter stays instant and only the URL waits.
  var urlPending;

  function syncUrl() {
    clearTimeout(urlPending);
    urlPending = setTimeout(function () {
      var params = new URLSearchParams(window.location.search);
      if (query.trim()) params.set('q', query.trim());
      else params.delete('q');
      // Once a search has been run the entry flag is stale; keeping it would
      // put a ?h= in a link that no longer points at anything on screen.
      params.delete('h');
      var qs = params.toString();
      // replaceState, not pushState: holding a key down should not bury the
      // previous page under thirty history entries.
      history.replaceState(null, '',
        window.location.pathname + (qs ? '?' + qs : '') + window.location.hash);
    }, 250);
  }

  function setQuery(value, opts) {
    query = value;
    render();
    if (!opts || opts.url !== false) syncUrl();
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
      if (e.key === 'Escape' && input.value && !(modal && modal.open)) {
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

  // A shared ?q= link arrives already filtered, with its results bar and its
  // cross-section group populated. Rendering once with no query does the same
  // job of keeping the DOM and this script in step from the first frame.
  var startQuery = (new URLSearchParams(window.location.search).get('q') || '').trim();
  if (startQuery && input) {
    input.value = startQuery;
    setQuery(startQuery, { url: false });
  } else {
    render();
  }

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



  /* --- Description popovers ----------------------------------------------
     Hover and keyboard focus are handled in CSS. This adds what CSS cannot:
     a tap target on touch devices, and Escape to dismiss. */

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('.info-btn');
    var open = document.querySelector('.card-info.is-open');

    if (open && (!btn || btn.parentElement !== open)) open.classList.remove('is-open');

    if (btn) {
      // Only meaningful where there is no hover; a mouse has already shown it.
      if (!window.matchMedia('(hover: hover)').matches) {
        ev.preventDefault();
        btn.parentElement.classList.toggle('is-open');
      }
    }
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    var open = document.querySelector('.card-info.is-open');
    if (open) open.classList.remove('is-open');
  });

  /* --- The link modal ----------------------------------------------------
     An entry with more than one link does not navigate. It opens a dialog
     listing every link, built from the <ul> already sitting in the card, so
     with JS off that same list is simply visible on the card instead. */

  var modal = document.querySelector('.link-modal');
  var modalTitle = document.getElementById('link-modal-title');
  var modalNote = document.querySelector('[data-modal-note]');
  var modalList = document.querySelector('[data-modal-list]');

  function openModal(card) {
    if (!modal || !modal.showModal) return false;   // no <dialog>: follow the links inline

    var title = card.querySelector('.card-title');
    var note = card.querySelector('.card-info .popover');
    var source = card.querySelector('.card-links');
    if (!source) return false;

    // data-title, not textContent: the button also carries a visually-hidden
    // ", N links" for screen readers, which does not belong in the heading.
    modalTitle.textContent = title ? (title.dataset.title || title.textContent) : '';

    if (note && note.textContent.trim()) {
      modalNote.textContent = note.textContent;
      modalNote.hidden = false;
    } else {
      modalNote.textContent = '';
      modalNote.hidden = true;
    }

    // Rebuild the list each time rather than keeping 34 dialogs in the DOM.
    modalList.replaceChildren();
    Array.prototype.forEach.call(source.children, function (item) {
      var anchor = item.querySelector('a');
      if (!anchor) return;

      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = anchor.href;
      if (anchor.target) { a.target = anchor.target; a.rel = anchor.rel; }

      var label = document.createElement('span');
      label.className = 'link-label';
      label.textContent = anchor.textContent;      // textContent, never innerHTML
      a.appendChild(label);

      var badge = item.querySelector('.badge');
      if (badge) a.appendChild(badge.cloneNode(true));

      var desc = item.querySelector('.link-note');
      if (desc) {
        var d = document.createElement('span');
        d.className = 'link-note';
        d.textContent = desc.textContent;
        a.appendChild(d);
      }

      li.appendChild(a);
      modalList.appendChild(li);
    });

    modal.showModal();
    // Focus the dialog itself, not its first link. Focusing an anchor paints
    // it as selected before the reader has chosen anything; the dialog still
    // traps focus, and Tab from here reaches the links in order.
    modal.focus();
    return true;
  }

  document.addEventListener('click', function (ev) {
    var trigger = ev.target.closest('[data-open-modal]');
    if (trigger) {
      var card = trigger.closest('.card');
      if (card && openModal(card)) ev.preventDefault();
      return;
    }
    if (ev.target.closest('[data-close-modal]') && modal) modal.close();
  });

  if (modal) {
    // Clicking the backdrop closes. The dialog itself fills its own box, so a
    // click landing directly on <dialog> is a click outside the panel.
    modal.addEventListener('click', function (ev) {
      if (ev.target === modal) modal.close();
    });
    // Following a link should not leave the dialog open behind it.
    modalList.addEventListener('click', function (ev) {
      if (ev.target.closest('a')) modal.close();
    });
  }

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

  /* --- Deep links --------------------------------------------------------
     ?h=<entry title> flags one card and scrolls to it, which is how a search
     result on another page lands you on the right entry. */

  var flag = new URLSearchParams(window.location.search).get('h');
  if (flag) {
    var wanted = flag.trim().toLowerCase();
    var match = cards.filter(function (card) {
      var t = card.querySelector('.card-title');
      return t && (t.dataset.title || t.textContent).trim().toLowerCase() === wanted;
    })[0];

    if (match) {
      match.classList.add('is-flagged');
      // A ?q= in the same URL may have filtered this card out; scrolling to
      // something hidden just jumps the page somewhere arbitrary.
      if (!match.hidden) {
        requestAnimationFrame(function () {
          match.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      }
    }
  }
})();
