// ─────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────
let results = [];
let lbIndex = -1;
let people  = [];
const activePeople = new Set();

// ─────────────────────────────────────────────
// DOM
// ─────────────────────────────────────────────
const form        = document.getElementById('search-form');
const queryInput  = document.getElementById('query');
const yearFrom    = document.getElementById('year-from');
const yearTo      = document.getElementById('year-to');
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
const lbDesc      = document.getElementById('lb-description');
const lbDescWrap  = document.getElementById('lb-desc-wrap');
const lbCounter   = document.getElementById('lb-counter');
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

async function doSearch() {
  const q = queryInput.value.trim();
  if (!q) return;

  showSkeletons();

  const params = new URLSearchParams({ q, limit: 50 });
  if (yearFrom.value) params.set('year_from', yearFrom.value);
  if (yearTo.value)   params.set('year_to',   yearTo.value);
  // When /search gains person_id support these will be picked up
  activePeople.forEach(id => params.append('person_id', id));

  try {
    const resp = await fetch(`/search?${params}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    results = data.results || [];
    renderResults();

    // Persist query in URL
    const url = new URL(location);
    url.searchParams.set('q', q);
    history.replaceState(null, '', url);
  } catch (err) {
    grid.innerHTML = '';
    setStatus(`Error: ${err.message}`);
  }
}

// ─────────────────────────────────────────────
// RENDER
// ─────────────────────────────────────────────
function renderResults() {
  grid.innerHTML = '';

  if (!results.length) {
    setStatus('No photos found.');
    showNoResults();
    return;
  }

  const n = results.length;
  setStatus(`${n} ${n === 1 ? 'photo' : 'photos'}`);

  results.forEach((r, i) => {
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

    const open = () => openLightbox(i);
    card.addEventListener('click', open);
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') open(); });

    grid.appendChild(card);
  });
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
