// ─────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────
let results = [];
let lbIndex = -1;
let people  = [];
const activePeople = new Set();
let peopleMode = 'any';
let currentOffset = 0;

// ─────────────────────────────────────────────
// DOM
// ─────────────────────────────────────────────
const form        = document.getElementById('search-form');
const queryInput  = document.getElementById('query');
const dayFrom     = document.getElementById('day-from');
const dayTo       = document.getElementById('day-to');
const dayToggle   = document.getElementById('day-toggle');
const grid        = document.getElementById('grid');
const statusBar   = document.getElementById('status');
const lightbox    = document.getElementById('lightbox');
const lbImg       = document.getElementById('lb-img');
const lbSpinner   = document.getElementById('lb-spinner');
const lbCaption   = document.getElementById('lb-caption');
const lbDate      = document.getElementById('lb-date');
const lbDateRow   = document.getElementById('lb-date-row');
const lbLocation  = document.getElementById('lb-location');
const lbLocRow    = document.getElementById('lb-location-row');
const lbPeople    = document.getElementById('lb-people');
const lbPeopleWrap= document.getElementById('lb-people-wrap');
const lbTags      = document.getElementById('lb-tags');
const lbTagsWrap  = document.getElementById('lb-tags-wrap');
const lbDesc          = document.getElementById('lb-description');
const lbDescWrap      = document.getElementById('lb-desc-wrap');
const lbAnalysisWrap  = document.getElementById('lb-analysis-wrap');
const lbAnalysisGrid  = document.getElementById('lb-analysis-grid');
const lbCounter       = document.getElementById('lb-counter');
const lbClose     = document.getElementById('lb-close');
const lbPrev      = document.getElementById('lb-prev');
const lbNext      = document.getElementById('lb-next');
const lbBackdrop  = document.getElementById('lb-backdrop');

// ─────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────
async function init() {
  setupNav();
  showEmptyState();
  await loadPeople();

  // Honor ?q= in URL on load
  const urlQ = new URLSearchParams(location.search).get('q');
  if (urlQ) {
    queryInput.value = urlQ;
    doSearch();
  }
}

// ─────────────────────────────────────────────
// NAV
// ─────────────────────────────────────────────
function setupNav() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.view').forEach(v => v.classList.remove('is-active'));
      btn.classList.add('active');
      document.getElementById(`view-${btn.dataset.view}`).classList.add('is-active');
    });
  });
}

// ─────────────────────────────────────────────
// PEOPLE  (GET /people — graceful fallback)
// ─────────────────────────────────────────────
async function loadPeople() {
  try {
    const resp = await fetch('/people');
    if (!resp.ok) return;
    people = await resp.json();
    if (people.length) renderPeopleFilter();
  } catch {
    // endpoint not yet implemented — filter stays hidden
  }
}

function renderPeopleFilter() {
  const filterRow = document.getElementById('people-filter');
  const chips     = document.getElementById('people-chips');
  filterRow.removeAttribute('hidden');
  chips.innerHTML = '';

  const modeBtn = document.createElement('button');
  modeBtn.type = 'button';
  modeBtn.className = 'mode-toggle';
  modeBtn.id = 'people-mode-toggle';
  modeBtn.textContent = 'Any';
  modeBtn.setAttribute('aria-label', 'People filter mode');
  modeBtn.addEventListener('click', () => {
    peopleMode = peopleMode === 'any' ? 'all' : 'any';
    modeBtn.textContent = peopleMode === 'any' ? 'Any' : 'All';
    modeBtn.classList.toggle('is-all', peopleMode === 'all');
  });
  filterRow.insertBefore(modeBtn, chips);

  people.forEach(p => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chip';
    btn.textContent = p.name.split(' ')[0];
    btn.dataset.id  = p.id;
    btn.setAttribute('aria-pressed', 'false');
    btn.addEventListener('click', () => {
      const active = activePeople.has(p.id);
      if (active) {
        activePeople.delete(p.id);
        btn.classList.remove('is-active');
        btn.setAttribute('aria-pressed', 'false');
      } else {
        activePeople.add(p.id);
        btn.classList.add('is-active');
        btn.setAttribute('aria-pressed', 'true');
      }
    });
    chips.appendChild(btn);
  });
}

// ─────────────────────────────────────────────
// SEARCH
// ─────────────────────────────────────────────
form.addEventListener('submit', e => { e.preventDefault(); doSearch(); });

// ─────────────────────────────────────────────
// MONTH/YEAR PICKER
// ─────────────────────────────────────────────
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

class MonthYearPicker {
  constructor(wrapEl) {
    this.wrap    = wrapEl;
    this.btn     = wrapEl.querySelector('.mypicker-btn');
    this.label   = wrapEl.querySelector('.mypicker-label');
    this.popup   = wrapEl.querySelector('.mypicker-popup');
    this.mGrid   = wrapEl.querySelector('.mp-months');
    this.yGrid   = wrapEl.querySelector('.mp-years');
    this.dLabel  = wrapEl.querySelector('.mp-decade-label');
    this.prevBtn = wrapEl.querySelector('.mp-prev');
    this.nextBtn = wrapEl.querySelector('.mp-next');
    this.manual  = wrapEl.querySelector('.mp-manual');
    this.clearBtn= wrapEl.querySelector('.mp-clear');

    this.month  = null;
    this.year   = null;
    this.decade = Math.floor(new Date().getFullYear() / 10) * 10;

    this._render();
    this._bind();
  }

  getValue() {
    if (this.month === null || this.year === null) return null;
    return `${this.year}-${String(this.month + 1).padStart(2, '0')}`;
  }

  clear() {
    this.month = null;
    this.year  = null;
    this.label.textContent = this.btn.getAttribute('aria-label') === 'From date' ? 'From…' : 'To…';
    this._render();
  }

  open() {
    this.popup.removeAttribute('hidden');
    this.btn.setAttribute('aria-expanded', 'true');
  }

  close() {
    this.popup.setAttribute('hidden', '');
    this.btn.setAttribute('aria-expanded', 'false');
  }

  toggle() {
    if (this.popup.hasAttribute('hidden')) this.open(); else this.close();
  }

  _updateLabel() {
    if (this.month !== null && this.year !== null) {
      this.label.textContent = `${MONTHS[this.month]} ${this.year}`;
    }
  }

  _maybeClose() {
    if (this.month !== null && this.year !== null) {
      this._updateLabel();
      this.close();
    }
  }

  _render() {
    this._renderMonths();
    this._renderYears();
  }

  _renderMonths() {
    this.mGrid.innerHTML = '';
    MONTHS.forEach((name, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'mp-month-btn' + (this.month === i ? ' sel' : '');
      b.textContent = name;
      b.addEventListener('click', () => {
        this.month = i;
        this._renderMonths();
        this._maybeClose();
      });
      this.mGrid.appendChild(b);
    });
  }

  _renderYears() {
    this.dLabel.textContent = `${this.decade}–${this.decade + 9}`;
    this.yGrid.innerHTML = '';
    for (let y = this.decade; y < this.decade + 12; y++) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'mp-year-btn' + (this.year === y ? ' sel' : '');
      b.textContent = y;
      b.addEventListener('click', () => {
        this.year = y;
        this.decade = Math.floor(y / 10) * 10;
        if (this.manual.value != y) this.manual.value = y;
        this._renderYears();
        this._maybeClose();
      });
      this.yGrid.appendChild(b);
    }
  }

  _bind() {
    this.btn.addEventListener('click', e => { e.stopPropagation(); this.toggle(); });

    this.prevBtn.addEventListener('click', e => {
      e.stopPropagation();
      this.decade -= 10;
      this._renderYears();
    });
    this.nextBtn.addEventListener('click', e => {
      e.stopPropagation();
      this.decade += 10;
      this._renderYears();
    });

    this.manual.addEventListener('input', () => {
      const v = parseInt(this.manual.value, 10);
      if (v >= 1900 && v <= 2099) {
        this.decade = Math.floor(v / 10) * 10;
        this._renderYears();
      }
    });
    this.manual.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const v = parseInt(this.manual.value, 10);
        if (v >= 1900 && v <= 2099) {
          this.year = v;
          this.decade = Math.floor(v / 10) * 10;
          this._renderYears();
          this._maybeClose();
        }
        e.preventDefault();
      }
    });
    this.manual.addEventListener('click', e => e.stopPropagation());

    this.clearBtn.addEventListener('click', e => {
      e.stopPropagation();
      this.clear();
      this.close();
    });
  }
}

const pickerFrom = new MonthYearPicker(document.getElementById('picker-from'));
const pickerTo   = new MonthYearPicker(document.getElementById('picker-to'));

document.addEventListener('click', e => {
  if (!pickerFrom.wrap.contains(e.target)) pickerFrom.close();
  if (!pickerTo.wrap.contains(e.target))   pickerTo.close();
});

dayToggle.addEventListener('click', () => {
  const pressed = dayToggle.getAttribute('aria-pressed') === 'true';
  const next = !pressed;
  dayToggle.setAttribute('aria-pressed', next ? 'true' : 'false');
  dayToggle.textContent = next ? '− day' : '+ day';
  if (next) { dayFrom.removeAttribute('hidden'); dayTo.removeAttribute('hidden'); }
  else { dayFrom.setAttribute('hidden', ''); dayTo.setAttribute('hidden', ''); dayFrom.value = ''; dayTo.value = ''; }
});

function _lastDayOfMonth(year, month) {
  return new Date(year, month, 0).getDate();
}

function _buildDate(monthVal, dayVal, side) {
  if (!monthVal) return null;
  const [y, m] = monthVal.split('-').map(Number);
  if (!y || !m) return null;
  let d;
  if (dayVal && dayVal.trim()) {
    d = Math.max(1, Math.min(31, parseInt(dayVal, 10)));
  } else {
    d = side === 'from' ? 1 : _lastDayOfMonth(y, m);
  }
  return `${String(y).padStart(4,'0')}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
}

function _buildSearchParams(offset = 0) {
  const q = queryInput.value.trim();
  const dFrom = _buildDate(pickerFrom.getValue(), dayFrom.value, 'from');
  const dTo   = _buildDate(pickerTo.getValue(),   dayTo.value,   'to');

  const params = new URLSearchParams({ limit: 50, offset });
  if (q)     params.set('q', q);
  if (dFrom) params.set('date_from', dFrom);
  if (dTo)   params.set('date_to',   dTo);
  activePeople.forEach(id => params.append('person_id', id));
  if (activePeople.size > 0 && peopleMode === 'all') {
    params.set('people_mode', 'all');
  }
  return params;
}

async function doSearch() {
  const params = _buildSearchParams(0);
  if (!params.has('q') && !params.has('date_from') && !params.has('date_to') && !params.has('person_id')) return;

  currentOffset = 0;
  showSkeletons();

  try {
    const resp = await fetch(`/search?${params}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    results = data.results || [];
    renderResults(data.has_more);

    const q = params.get('q');
    const url = new URL(location);
    if (q) url.searchParams.set('q', q);
    else   url.searchParams.delete('q');
    history.replaceState(null, '', url);
  } catch (err) {
    grid.innerHTML = '';
    setStatus(`Error: ${err.message}`);
  }
}

async function loadMore() {
  currentOffset += 50;
  const params = _buildSearchParams(currentOffset);
  const btn = document.getElementById('load-more-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }

  try {
    const resp = await fetch(`/search?${params}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const newResults = data.results || [];
    results = results.concat(newResults);
    appendResults(newResults, data.has_more);
    setStatus(`${results.length} photos`);
  } catch (err) {
    setStatus(`Error: ${err.message}`);
    if (btn) { btn.disabled = false; btn.textContent = 'Load more'; }
  }
}

// ─────────────────────────────────────────────
// RENDER
// ─────────────────────────────────────────────
function _makeCard(r, index) {
  const card = document.createElement('div');
  card.className = 'card';
  card.setAttribute('role', 'listitem');
  card.tabIndex = 0;
  card.setAttribute('aria-label', r.caption || 'Family photo');

  const wrap = document.createElement('div');
  wrap.className = 'card-img-wrap';

  const img = document.createElement('img');
  img.className  = 'card-img';
  img.src        = r.thumb_url;
  img.alt        = r.caption || '';
  img.loading    = 'lazy';
  img.decoding   = 'async';
  wrap.appendChild(img);

  const badgeText = r.sharpness === 'very_blurry'    ? 'blurry'
                  : r.sharpness === 'slightly_blurry' ? '~blurry'
                  : r.content_type === 'document'     ? 'doc'
                  : r.content_type === 'other'        ? 'other'
                  : null;
  if (badgeText) {
    const badge = document.createElement('span');
    badge.className = 'card-badge' + (r.sharpness === 'very_blurry' ? ' card-badge--red' : '');
    badge.textContent = badgeText;
    wrap.appendChild(badge);
  }

  const info = document.createElement('div');
  info.className = 'card-info';

  if (r.caption) {
    const cap = document.createElement('div');
    cap.className   = 'card-caption';
    cap.textContent = r.caption;
    info.appendChild(cap);
  }

  if (r.taken_at) {
    const d = document.createElement('div');
    d.className   = 'card-date';
    d.textContent = fmtDate(r.taken_at);
    info.appendChild(d);
  }

  card.appendChild(wrap);
  card.appendChild(info);

  const open = () => openLightbox(index);
  card.addEventListener('click', open);
  card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') open(); });

  return card;
}

function _renderLoadMore(has_more) {
  const existing = document.getElementById('load-more-btn');
  if (existing) existing.remove();
  if (!has_more) return;

  const btn = document.createElement('button');
  btn.id        = 'load-more-btn';
  btn.className = 'load-more-btn';
  btn.textContent = 'Load more';
  btn.addEventListener('click', loadMore);
  grid.after(btn);
}

function renderResults(has_more = false) {
  grid.innerHTML = '';
  document.getElementById('load-more-btn')?.remove();

  if (!results.length) {
    setStatus('No photos found.');
    showNoResults();
    return;
  }

  const n = results.length;
  setStatus(`${n} ${n === 1 ? 'photo' : 'photos'}`);

  results.forEach((r, i) => grid.appendChild(_makeCard(r, i)));
  _renderLoadMore(has_more);
}

function appendResults(newResults, has_more) {
  const startIndex = results.length - newResults.length;
  newResults.forEach((r, i) => grid.appendChild(_makeCard(r, startIndex + i)));
  _renderLoadMore(has_more);
}

function showSkeletons(count = 9) {
  grid.innerHTML = Array.from({ length: count }, () => `
    <div class="card skeleton" aria-hidden="true">
      <div class="card-img-wrap skeleton-img"></div>
      <div class="card-info">
        <div class="skeleton-line"></div>
        <div class="skeleton-line short"></div>
      </div>
    </div>
  `).join('');
  setStatus('Searching…');
}

function showEmptyState() {
  const suggestions = [
    'grandma at the beach',
    'birthday party',
    'family vacation',
    'everyone smiling',
    'summer holidays',
    'old photos',
  ];
  grid.innerHTML = `
    <div class="empty-state">
      <span class="empty-icon" aria-hidden="true">📷</span>
      <p class="empty-headline">Search the family archive</p>
      <p class="empty-hint">Describe a memory, a person, or a place</p>
      <div class="suggestion-list" role="list">
        ${suggestions.map(s =>
          `<button class="suggestion" type="button" role="listitem">${s}</button>`
        ).join('')}
      </div>
    </div>
  `;
  grid.querySelectorAll('.suggestion').forEach(btn => {
    btn.addEventListener('click', () => {
      queryInput.value = btn.textContent;
      doSearch();
    });
  });
  setStatus('');
}

function showNoResults() {
  grid.innerHTML = `
    <div class="empty-state">
      <span class="empty-icon" aria-hidden="true">🔍</span>
      <p class="empty-headline">No photos found</p>
      <p class="empty-hint">Try different words or remove some filters</p>
    </div>
  `;
}

function setStatus(text) {
  statusBar.textContent  = text;
  statusBar.style.opacity = text ? '1' : '0';
}

// ─────────────────────────────────────────────
// LIGHTBOX
// ─────────────────────────────────────────────
async function openLightbox(index) {
  lbIndex = index;
  const r = results[index];

  // Reset
  lbImg.src        = '';
  lbSpinner.classList.remove('hidden');
  lbCaption.textContent = r.caption || '';
  setLbDate(r.taken_at);
  lbLocRow.setAttribute('hidden', '');
  lbPeopleWrap.setAttribute('hidden', '');
  lbTagsWrap.setAttribute('hidden', '');
  lbDescWrap.setAttribute('hidden', '');
  lbAnalysisWrap.setAttribute('hidden', '');
  lbAnalysisGrid.innerHTML = '';
  updateLbCounter();
  updateNavBtns();

  lightbox.removeAttribute('hidden');
  lbClose.focus();

  // Load full photo
  const tempImg = new Image();
  tempImg.onload = () => {
    lbImg.src = tempImg.src;
    lbSpinner.classList.add('hidden');
  };
  tempImg.onerror = () => { lbSpinner.classList.add('hidden'); };
  tempImg.src = `/photo/${r.id}`;

  // Apply any enriched data already in the result (future API)
  applyRichData(r);

  // Try enriched /info endpoint (future)
  try {
    const resp = await fetch(`/photo/${r.id}/info`);
    if (resp.ok) {
      const info = await resp.json();
      applyRichData(info);
    }
  } catch {
    // not yet available
  }
}

function applyRichData(data) {
  if (data.location_name) {
    lbLocation.textContent = data.location_name;
    lbLocRow.removeAttribute('hidden');
  }
  if (data.people?.length) {
    lbPeople.innerHTML = data.people
      .map(p => `<span class="lb-person">${p.name || p}</span>`)
      .join('');
    lbPeopleWrap.removeAttribute('hidden');
  }
  if (data.tags?.length) {
    lbTags.innerHTML = data.tags
      .map(t => `<span class="lb-tag">${t}</span>`)
      .join('');
    lbTagsWrap.removeAttribute('hidden');
  }
  if (data.description) {
    lbDesc.textContent = data.description;
    lbDescWrap.removeAttribute('hidden');
  }

  const analysisFields = [
    { key: 'subject_type',      label: 'subject' },
    { key: 'primary_focus',     label: 'focus' },
    { key: 'setting_type',      label: 'setting' },
    { key: 'indoor_outdoor',    label: 'in/out' },
    { key: 'sharpness',         label: 'sharpness' },
    { key: 'face_clarity_score',label: 'face' },
    { key: 'content_type',      label: 'type' },
  ];
  lbAnalysisGrid.innerHTML = '';
  analysisFields.forEach(({ key, label }) => {
    const val = data[key];
    if (val == null) return;
    const row = document.createElement('div');
    row.className = 'lb-analysis-row';
    const lbl = document.createElement('span');
    lbl.className = 'lb-analysis-label';
    lbl.textContent = label;
    const chip = document.createElement('span');
    chip.className = 'lb-analysis-chip';

    if (key === 'sharpness') {
      chip.classList.add(
        val === 'sharp'           ? 'lb-analysis-chip--green'
        : val === 'very_blurry'   ? 'lb-analysis-chip--red'
        : 'lb-analysis-chip--amber'
      );
      chip.textContent = val.replace(/_/g, ' ');
    } else if (key === 'face_clarity_score') {
      const score = Number(val);
      chip.classList.add(
        score >= 4 ? 'lb-analysis-chip--green'
        : score === 3 ? 'lb-analysis-chip--amber'
        : 'lb-analysis-chip--red'
      );
      chip.textContent = '●'.repeat(score) + '○'.repeat(5 - score) + ' ' + score;
    } else if (key === 'content_type' && val !== 'photo') {
      chip.classList.add('lb-analysis-chip--amber');
      chip.textContent = val;
    } else {
      chip.textContent = val.replace(/_/g, ' ');
    }

    row.appendChild(lbl);
    row.appendChild(chip);
    lbAnalysisGrid.appendChild(row);
  });
  if (lbAnalysisGrid.children.length > 0) lbAnalysisWrap.removeAttribute('hidden');
}

function setLbDate(takenAt) {
  if (takenAt) {
    lbDate.textContent = fmtDate(takenAt, true);
    lbDateRow.removeAttribute('hidden');
  } else {
    lbDateRow.setAttribute('hidden', '');
  }
}

function closeLightbox() {
  lightbox.setAttribute('hidden', '');
  lbImg.src = '';
  lbIndex   = -1;
}

function navigateLightbox(dir) {
  const next = lbIndex + dir;
  if (next >= 0 && next < results.length) openLightbox(next);
}

function updateNavBtns() {
  lbPrev.classList.toggle('hidden', lbIndex <= 0);
  lbNext.classList.toggle('hidden', lbIndex >= results.length - 1);
}

function updateLbCounter() {
  if (results.length > 1) {
    lbCounter.textContent = `${lbIndex + 1} of ${results.length}`;
  } else {
    lbCounter.textContent = '';
  }
}

// Lightbox events
lbClose.addEventListener('click', closeLightbox);
lbBackdrop.addEventListener('click', closeLightbox);
lbPrev.addEventListener('click', () => navigateLightbox(-1));
lbNext.addEventListener('click', () => navigateLightbox(1));

document.addEventListener('keydown', e => {
  if (lightbox.hasAttribute('hidden')) return;
  if (e.key === 'Escape')      closeLightbox();
  if (e.key === 'ArrowLeft')   navigateLightbox(-1);
  if (e.key === 'ArrowRight')  navigateLightbox(1);
});

// Touch swipe for mobile lightbox
let touchX0 = 0;
lightbox.addEventListener('touchstart', e => {
  touchX0 = e.touches[0].clientX;
}, { passive: true });
lightbox.addEventListener('touchend', e => {
  const dx = e.changedTouches[0].clientX - touchX0;
  if (Math.abs(dx) > 50) navigateLightbox(dx > 0 ? -1 : 1);
}, { passive: true });

// ─────────────────────────────────────────────
// UTILS
// ─────────────────────────────────────────────
function fmtDate(str, long = false) {
  if (!str) return '';
  try {
    const d = new Date(str);
    if (isNaN(d)) return str.slice(0, 10);
    return long
      ? d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
      : d.toLocaleDateString('en-US', { year: 'numeric', month: 'short' });
  } catch {
    return str.slice(0, 10);
  }
}

// ─────────────────────────────────────────────
// GO
// ─────────────────────────────────────────────
init();
