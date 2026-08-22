/* Guided Meditations — progressive enhancement only.
   Every page is complete without this file: pagination is real links, cards are
   real anchors, and audio falls back to the source podcast page. */

(function () {
  'use strict';

  var root = document.documentElement;

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  /* ---------------- Theme ---------------- */

  function initTheme() {
    var toggle = $('.theme-toggle');
    if (!toggle) return;
    toggle.addEventListener('click', function () {
      var systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      var current = root.getAttribute('data-theme') || (systemDark ? 'dark' : 'light');
      var next = current === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('gm-theme', next); } catch (e) { /* private mode */ }
      toggle.setAttribute('aria-label', next === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    });
  }

  /* ---------------- Collapsing header ---------------- */

  // Scroll position with hysteresis, deliberately not an IntersectionObserver on
  // a sentinel: collapsing the header shortens it, which moves any sentinel below
  // it back into view and flips the state straight back — an endless flicker.
  // Scroll position does not move when the document reflows, so it cannot loop.
  var COLLAPSE_AT = 150;
  var EXPAND_AT = 40;

  function initHeader() {
    var header = $('.site-header');
    if (!header) return;
    var compact = false;
    var ticking = false;

    function update() {
      ticking = false;
      var y = window.scrollY || window.pageYOffset || 0;
      if (!compact && y > COLLAPSE_AT) { compact = true; header.classList.add('is-compact'); }
      else if (compact && y < EXPAND_AT) { compact = false; header.classList.remove('is-compact'); }
    }

    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    }, { passive: true });
    update();
  }

  /* ---------------- Broken podcast artwork ---------------- */

  function initArtwork() {
    $$('.podcast-art img').forEach(function (img) {
      img.addEventListener('error', function () { img.classList.add('is-broken'); });
      if (img.complete && img.naturalWidth === 0) img.classList.add('is-broken');
    });
  }

  /* ---------------- Audio ---------------- */

  var audio = null;
  var playerBar = null;
  var activeButton = null;

  function formatTime(seconds) {
    if (!isFinite(seconds)) return '0:00';
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  function initAudio() {
    playerBar = $('.player-bar');
    if (!playerBar) return;

    audio = new Audio();
    audio.preload = 'none';

    var toggle = $('.player-toggle', playerBar);
    var scrub = $('.player-scrub', playerBar);
    var title = $('.player-title', playerBar);
    var sub = $('.player-sub', playerBar);
    var time = $('.player-time', playerBar);
    var close = $('.player-close', playerBar);
    var scrubbing = false;

    function setPlayingState(on) {
      playerBar.classList.toggle('is-playing', on);
      toggle.setAttribute('aria-label', on ? 'Pause' : 'Play');
      if (activeButton) {
        activeButton.classList.toggle('is-playing', on);
        activeButton.setAttribute('aria-pressed', on ? 'true' : 'false');
        var label = $('.play-label', activeButton);
        if (label) label.textContent = on ? 'Pause' : 'Play';
      }
    }

    audio.addEventListener('play', function () { setPlayingState(true); });
    audio.addEventListener('pause', function () { setPlayingState(false); });
    audio.addEventListener('ended', function () { setPlayingState(false); });
    audio.addEventListener('timeupdate', function () {
      if (scrubbing || !audio.duration) return;
      scrub.value = String((audio.currentTime / audio.duration) * 100);
      time.textContent = formatTime(audio.currentTime) + ' / ' + formatTime(audio.duration);
    });
    audio.addEventListener('error', function () {
      sub.textContent = 'This recording could not be loaded — try the podcast page.';
      setPlayingState(false);
    });

    scrub.addEventListener('input', function () { scrubbing = true; });
    scrub.addEventListener('change', function () {
      if (audio.duration) audio.currentTime = (Number(scrub.value) / 100) * audio.duration;
      scrubbing = false;
    });
    toggle.addEventListener('click', function () {
      if (audio.paused) { audio.play().catch(function () {}); } else { audio.pause(); }
    });
    close.addEventListener('click', function () {
      audio.pause();
      playerBar.classList.remove('is-visible');
      playerBar.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('has-player');
      if (activeButton) { activeButton.classList.remove('is-playing'); activeButton = null; }
    });

    document.addEventListener('click', function (event) {
      var button = event.target.closest ? event.target.closest('.play-btn') : null;
      if (!button) return;
      event.preventDefault();
      var src = button.getAttribute('data-audio');
      if (!src) return;

      if (activeButton === button && !audio.paused) { audio.pause(); return; }
      if (activeButton === button && audio.paused && audio.src) { audio.play().catch(function () {}); return; }

      if (activeButton) activeButton.classList.remove('is-playing');
      activeButton = button;
      audio.src = src;
      title.textContent = button.getAttribute('data-title') || 'Guided meditation';
      sub.textContent = button.getAttribute('data-sub') || '';
      time.textContent = '0:00';
      scrub.value = '0';
      playerBar.hidden = false;
      playerBar.setAttribute('aria-hidden', 'false');
      document.body.classList.add('has-player');
      // Next frame, so the transform transition actually runs.
      window.requestAnimationFrame(function () { playerBar.classList.add('is-visible'); });
      audio.play().catch(function () {});
    });
  }

  /* ---------------- Filtering ---------------- */

  function initFilters() {
    var form = $('.filters');
    if (!form) return;

    var list = $('#meditation-list');
    var status = $('#filter-status');
    var empty = $('#empty-state');
    var reset = $('.reset-filters');
    var pagination = $('.pagination');
    var searchInput = $('#filter-search');
    var clearSearch = $('.search-clear');
    var sourceSelect = $('#filter-source');
    var lengthSelect = $('#filter-length');
    var practiceSelect = $('#filter-practice');
    var toggle = $('.filter-toggle', form);
    var fields = $('#filter-fields', form);
    var indexUrl = form.getAttribute('data-index');

    function setExpanded(open) {
      if (!toggle || !fields) return;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      fields.hidden = !open;
    }

    var cards = $$('.meditation', list);
    var searchIndex = null;
    var searchLicences = [];
    var indexPending = false;
    var totalOnPage = cards.length;

    function state() {
      return {
        q: (searchInput && searchInput.value || '').trim().toLowerCase(),
        source: sourceSelect ? sourceSelect.value : '',
        length: lengthSelect ? lengthSelect.value : '',
        practice: practiceSelect ? practiceSelect.value : ''
      };
    }

    function isActive(s) {
      return !!(s.q || s.source || s.length || s.practice);
    }

    function matchesCard(card, s) {
      if (s.source && card.dataset.source !== s.source) return false;
      if (s.length && card.dataset.length !== s.length) return false;
      if (s.practice && (card.dataset.practices || '').split(' ').indexOf(s.practice) === -1) return false;
      if (s.q && (card.dataset.search || '').indexOf(s.q) === -1) return false;
      return true;
    }

    function matchesRecord(rec, s) {
      if (s.source && rec.f !== s.source) return false;
      if (s.length && rec.b !== s.length) return false;
      if (s.practice && (rec.p || []).indexOf(s.practice) === -1) return false;
      if (s.q && (rec.t + ' ' + (rec.e || '') + ' ' + (rec.n || '')).toLowerCase().indexOf(s.q) === -1) return false;
      return true;
    }

    function announce(shown, total, scope) {
      if (!status) return;
      if (shown === 0) {
        status.textContent = 'No meditations match these filters.';
      } else {
        status.textContent = 'Showing ' + shown + ' of ' + total + ' meditations' + scope + '.';
      }
    }

    function renderRecords(records) {
      var html = records.map(function (rec) {
        var meta = [
          rec.n ? '<span class="meditation-source">' + escapeHtml(rec.n) + '</span>' : '',
          rec.e ? escapeHtml(rec.e) : '',
          rec.d ? escapeHtml(rec.d) : ''
        ].filter(Boolean).join(' <span class="meta-dot" aria-hidden="true"></span> ');
        var play = rec.a
          ? '<div class="meditation-actions"><button type="button" class="play-btn" data-audio="' + escapeHtml(rec.a) +
            '" data-title="' + escapeHtml(rec.t) + '" data-sub="' + escapeHtml(rec.e || rec.n || '') +
            '" aria-pressed="false"><svg class="icon-play" viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M4 2.5v11l9-5.5z"/></svg>' +
            '<svg class="icon-pause" viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M4 2.5h3v11H4zm5 0h3v11H9z"/></svg>' +
            '<span class="play-label">Play</span></button></div>'
          : '';
        // Attribution and licence must travel with a result, not just with a
        // server-rendered card.
        var lic = searchLicences[rec.l];
        var licence = lic
          ? '<p class="licence-note">Shared under <a href="' + escapeHtml(lic.u) +
            '" rel="license nofollow noopener" target="_blank">' + escapeHtml(lic.n) + '</a></p>'
          : '';
        return '<li class="meditation"><div class="meditation-content">' +
          '<div class="meditation-meta">' + meta + '</div>' +
          '<h2 class="meditation-title"><a class="meditation-link" href="' + escapeHtml(rec.u) + '">' + escapeHtml(rec.t) + '</a></h2>' +
          play + licence + '</div></li>';
      }).join('');
      list.innerHTML = html;
    }

    function escapeHtml(value) {
      return String(value == null ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function applyLocal(s) {
      var shown = 0;
      cards.forEach(function (card) {
        var ok = matchesCard(card, s);
        card.classList.toggle('hidden', !ok);
        if (ok) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
      announce(shown, totalOnPage, ' on this page');
      return shown;
    }

    function applyIndex(s) {
      var hits = searchIndex.filter(function (rec) { return matchesRecord(rec, s); });
      var capped = hits.slice(0, 120);
      renderRecords(capped);
      if (empty) empty.hidden = hits.length !== 0;
      announce(capped.length, hits.length, hits.length > capped.length
        ? ' across the whole archive (first ' + capped.length + ' shown)' : ' across the whole archive');
      return hits.length;
    }

    function restoreServerList() {
      if (list.dataset.serverHtml) {
        list.innerHTML = list.dataset.serverHtml;
        cards = $$('.meditation', list);
      }
    }

    function apply(pushUrl) {
      var s = state();
      var active = isActive(s);

      if (clearSearch) clearSearch.hidden = !s.q;
      if (reset) reset.hidden = !active;
      if (pagination) pagination.classList.toggle('hidden', active);

      if (!active) {
        restoreServerList();
        cards.forEach(function (card) { card.classList.remove('hidden'); });
        if (empty) empty.hidden = true;
        if (status) status.textContent = '';
      } else if (indexUrl && searchIndex) {
        applyIndex(s);
      } else if (indexUrl) {
        applyLocal(s);
        if (status) status.textContent += ' Searching the full archive…';
        loadIndex();
      } else {
        applyLocal(s);
      }

      if (pushUrl) syncUrl(s);
    }

    function syncUrl(s) {
      if (!window.history || !window.history.replaceState) return;
      var params = new URLSearchParams();
      if (s.q) params.set('q', s.q);
      if (s.source) params.set('source', s.source);
      if (s.length) params.set('length', s.length);
      if (s.practice) params.set('practice', s.practice);
      var query = params.toString();
      window.history.replaceState(null, '', query ? '?' + query : window.location.pathname);
    }

    function readUrl() {
      var params = new URLSearchParams(window.location.search);
      if (searchInput && params.get('q')) searchInput.value = params.get('q');
      if (sourceSelect && params.get('source')) sourceSelect.value = params.get('source');
      if (lengthSelect && params.get('length')) lengthSelect.value = params.get('length');
      if (practiceSelect && params.get('practice')) practiceSelect.value = params.get('practice');
    }

    list.dataset.serverHtml = list.innerHTML;

    function loadIndex() {
      if (!indexUrl || searchIndex || indexPending) return;
      indexPending = true;
      fetch(indexUrl)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          searchIndex = data.items || data;
          searchLicences = data.licences || [];
          indexPending = false;
          if (isActive(state())) apply(false);
        })
        .catch(function () { indexPending = false; indexUrl = null; });
    }

    var debounce;
    if (searchInput) {
      searchInput.addEventListener('focus', loadIndex, { once: true });
      searchInput.addEventListener('input', function () {
        window.clearTimeout(debounce);
        debounce = window.setTimeout(function () { apply(true); }, 180);
      });
    }
    if (clearSearch) {
      clearSearch.addEventListener('click', function () {
        searchInput.value = '';
        searchInput.focus();
        apply(true);
      });
    }
    form.addEventListener('pointerenter', loadIndex, { once: true });
    if (toggle) {
      toggle.addEventListener('click', function () {
        setExpanded(toggle.getAttribute('aria-expanded') !== 'true');
        loadIndex();
      });
    }
    [sourceSelect, lengthSelect, practiceSelect].forEach(function (select) {
      if (select) select.addEventListener('change', function () { apply(true); });
    });
    if (reset) {
      reset.addEventListener('click', function () {
        if (searchInput) searchInput.value = '';
        [sourceSelect, lengthSelect, practiceSelect].forEach(function (select) {
          if (select) select.value = '';
        });
        apply(true);
        if (searchInput) searchInput.focus();
      });
    }

    form.hidden = false;
    readUrl();
    var initial = state();
    // A filter arriving in the URL — from a practice tag, or a shared link —
    // opens the panel so the reader can see what is already narrowing the list.
    if (initial.length || initial.practice || initial.source) setExpanded(true);
    if (isActive(initial)) apply(false);
  }

  /* ---------------- Go ---------------- */

  function init() {
    initTheme();
    initHeader();
    initArtwork();
    initAudio();
    initFilters();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
