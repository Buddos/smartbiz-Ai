document.addEventListener('DOMContentLoaded', () => {
  const csrf = document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  const action = (url) => fetch(url, {method: 'POST', headers: {'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest'}}).then(r => r.ok ? refresh() : r.json().then(d => alert(d.error || 'Unable to update the chair.')));
  const bind = () => {
    document.querySelectorAll('[data-seat]').forEach(el => el.onclick = () => action(`chairs/${el.dataset.seat}/seat-next/`));
    document.querySelectorAll('[data-finish]').forEach(el => el.onclick = () => action(`appointments/${el.dataset.finish}/finish/`));
  };
  const refresh = () => fetch('api/live-floor/', {headers: {'X-Requested-With': 'XMLHttpRequest'}}).then(r => r.json()).then(data => {
    Object.entries(data.metrics).forEach(([key, value]) => document.querySelectorAll(`[data-metric="${key}"]`).forEach(el => el.textContent = key === 'revenue' ? Number(value).toLocaleString() : value));
    const board = document.querySelector('#chairBoard');
    if (board) board.innerHTML = data.chairs.map(chair => `<article class="barber-chair-card"><span class="barber-chair-state is-${escapeHtml(chair.status)}">${escapeHtml(chair.status)}</span><strong>${escapeHtml(chair.label)}</strong><small>${escapeHtml(chair.barber)}</small><div class="barber-chair-client">${chair.client ? `<b>${escapeHtml(chair.client)}</b><span>${escapeHtml(chair.service)}</span><button class="barber-floor-action" data-finish="${escapeHtml(chair.appointment_id)}">Finish</button>` : `<span>Available</span><button class="barber-floor-action" data-seat="${escapeHtml(chair.id)}">Seat next</button>`}</div></article>`).join('') || '<p class="salon-muted-copy">Add chairs and assign barbers to begin live chair tracking.</p>';
    const queue = document.querySelector('#queueList');
    if (queue) queue.innerHTML = data.queue.map((client, index) => `<div class="salon-sale-row"><span class="salon-sale-avatar">${index + 1}</span><span class="salon-sale-person"><strong>${escapeHtml(client.name)}</strong><small>${escapeHtml(client.service)} · ${escapeHtml(client.barber)}</small></span><span class="salon-sale-total">${escapeHtml(client.wait)}m<small>waiting</small></span></div>`).join('') || '<p class="salon-muted-copy">Nobody is waiting right now.</p>';
    bind();
  });
  bind(); setInterval(refresh, 30000);
});
