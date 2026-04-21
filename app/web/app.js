const form = document.getElementById('search-form');
const queryInput = document.getElementById('query');
const yearFrom = document.getElementById('year-from');
const yearTo = document.getElementById('year-to');
const grid = document.getElementById('grid');
const status = document.getElementById('status');
const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightbox-img');
const lightboxCaption = document.getElementById('lightbox-caption');
const closeBtn = document.getElementById('close-btn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = queryInput.value.trim();
  if (!q) return;

  status.textContent = 'Searching…';
  grid.innerHTML = '';

  const params = new URLSearchParams({ q, limit: 50 });
  if (yearFrom.value) params.set('year_from', yearFrom.value);
  if (yearTo.value) params.set('year_to', yearTo.value);

  try {
    const resp = await fetch(`/search?${params}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderResults(data.results);
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
  }
});

function renderResults(results) {
  if (!results.length) {
    status.textContent = 'No results.';
    return;
  }
  status.textContent = `${results.length} result${results.length === 1 ? '' : 's'}`;

  for (const r of results) {
    const card = document.createElement('div');
    card.className = 'card';

    const img = document.createElement('img');
    img.src = r.thumb_url;
    img.alt = r.caption || '';
    img.loading = 'lazy';

    const info = document.createElement('div');
    info.className = 'card-info';

    if (r.caption) {
      const cap = document.createElement('div');
      cap.className = 'card-caption';
      cap.textContent = r.caption;
      info.appendChild(cap);
    }

    if (r.taken_at) {
      const date = document.createElement('div');
      date.className = 'card-date';
      date.textContent = r.taken_at.slice(0, 10);
      info.appendChild(date);
    }

    card.appendChild(img);
    card.appendChild(info);
    card.addEventListener('click', () => openLightbox(r));
    grid.appendChild(card);
  }
}

function openLightbox(r) {
  lightboxImg.src = `/photo/${r.id}`;
  lightboxCaption.textContent = r.caption || '';
  lightbox.classList.remove('hidden');
}

function closeLightbox() {
  lightbox.classList.add('hidden');
  lightboxImg.src = '';
}

closeBtn.addEventListener('click', closeLightbox);
lightbox.addEventListener('click', (e) => {
  if (e.target === lightbox) closeLightbox();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeLightbox();
});
