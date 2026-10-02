document.addEventListener('DOMContentLoaded', () => {
  const page = document.getElementById('barberBoardPage');
  const board = document.getElementById('chairBoard');
  const queueList = document.getElementById('boardQueue');
  const dateInput = document.getElementById('boardDate');
  if (!page || !board || !queueList || !dateInput) return;

  const csrf = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1];
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[character]));
  let boardData = null;
  let selectedView = 'chairs';

  const parseDate = (value) => {
    const [year, month, day] = value.split('-').map(Number);
    return new Date(year, month - 1, day);
  };
  const inputDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  const formatDate = (value) => parseDate(value).toLocaleDateString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  });
  const formatTime = (value) => new Date(value).toLocaleTimeString([], {
    hour: 'numeric', minute: '2-digit',
  });
  const statusClass = (status) => ({
    BOOKED: 'booked', CONFIRMED: 'confirmed', WAITING: 'waiting',
    IN_CHAIR: 'in-chair', DONE: 'done', NO_SHOW: 'no-show', CANCELLED: 'cancelled',
  }[status] || 'booked');
  const activeAppointments = () => boardData?.appointments || [];

  const updateMetrics = (metrics) => {
    Object.entries(metrics || {}).forEach(([key, value]) => {
      document.querySelectorAll(`[data-metric="${key}"]`).forEach((element) => {
        element.textContent = key === 'revenue' ? Number(value).toLocaleString() : value;
      });
    });
  };

  const matchesSearch = (values) => {
    const query = document.getElementById('boardSearch').value.trim().toLocaleLowerCase();
    return !query || values.some((value) => String(value || '').toLocaleLowerCase().includes(query));
  };

  const renderChairs = () => {
    const chairs = boardData?.chairs || [];
    const appointments = activeAppointments();
    if (!chairs.length) {
      board.innerHTML = '<p class="board-empty">No chairs set up yet. Add chairs in settings to start live chair tracking.</p>';
      return;
    }
    board.innerHTML = chairs.map((chair) => {
      const chairAppointments = appointments.filter((appointment) => appointment.chair_id === chair.id);
      const visibleAppointments = chairAppointments.filter((appointment) => matchesSearch([
        appointment.client, appointment.phone, appointment.service, appointment.barber,
      ]));
      if (document.getElementById('boardSearch').value.trim() && !matchesSearch([chair.label, chair.barber]) && !visibleAppointments.length) {
        return '';
      }
      const status = chair.status === 'busy' ? 'in-chair' : chair.status;
      const cards = visibleAppointments.map((appointment) => `
        <button type="button" class="board-appointment-card is-${statusClass(appointment.status)}" data-open-detail="${escapeHtml(appointment.id)}">
          <span class="board-appointment-time">${escapeHtml(formatTime(appointment.start_time))}</span>
          <strong>${escapeHtml(appointment.client)}</strong>
          <span>${escapeHtml(appointment.service)} · KSh ${Number(appointment.price).toLocaleString()}</span>
          <span class="board-appointment-meta">${escapeHtml(appointment.status_label)} · ${Number(appointment.duration)} min</span>
          ${appointment.status === 'IN_CHAIR' ? '<span class="board-live-timer" data-started-at="' + escapeHtml(appointment.started_at || appointment.start_time) + '"></span>' : ''}
        </button>`).join('');
      return `<article class="board-chair-lane">
        <header><div><strong>${escapeHtml(chair.label)}</strong><span>${escapeHtml(chair.barber)}</span></div><span class="barber-chair-state is-${escapeHtml(status)}">${escapeHtml(chair.status)}</span></header>
        <div class="board-appointment-stack">${cards || '<p class="board-lane-empty">No appointments on this chair.</p>'}</div>
        ${chair.status !== 'busy' ? `<button type="button" class="barber-floor-action" data-seat-chair="${escapeHtml(chair.id)}">Seat next</button>` : ''}
      </article>`;
    }).join('');
    if (!board.innerHTML.trim()) {
      board.innerHTML = '<p class="board-empty">No chair appointments match your search.</p>';
    }
  };

  const renderQueue = () => {
    const queue = (boardData?.queue || []).filter((client) => matchesSearch([
      client.name, client.phone, client.service, client.barber,
    ]));
    queueList.innerHTML = queue.length ? queue.map((client, index) => {
      const availableChair = (boardData?.chairs || []).find((chair) => chair.status !== 'busy' && chair.status !== 'break');
      return `<article class="board-queue-row">
        <span class="board-queue-number">${index + 1}</span>
        <div class="board-queue-client"><strong>${escapeHtml(client.name)}</strong><span>${escapeHtml(client.service)} · ${escapeHtml(client.barber)}</span></div>
        <strong class="board-queue-wait">${Number(client.wait)} min</strong>
        <button type="button" class="barber-floor-action" data-seat-chair="${escapeHtml(availableChair?.id || '')}" ${availableChair ? '' : 'disabled'}>Seat next</button>
      </article>`;
    }).join('') : '<p class="board-empty">Queue is empty. Everyone has been served.</p>';
  };

  const updateView = () => {
    const chairView = selectedView === 'chairs';
    board.hidden = !chairView;
    queueList.hidden = chairView;
    document.querySelectorAll('[data-board-view]').forEach((button) => {
      const active = button.dataset.boardView === selectedView;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    });
    document.getElementById('boardDateHeading').textContent = chairView
      ? `Chairs · ${formatDate(dateInput.value)}`
      : `Today's queue · ${(boardData?.queue || []).length}`;
    renderChairs();
    renderQueue();
    const dock = document.getElementById('queueDock');
    const nextClient = boardData?.queue?.[0];
    dock.hidden = !nextClient;
    if (nextClient) {
      document.getElementById('nextQueueSummary').textContent = `Next up: ${nextClient.name} · ${nextClient.service}`;
      const nextChair = (boardData.chairs || []).find((chair) => chair.status !== 'busy' && chair.status !== 'break');
      document.getElementById('seatNextButton').disabled = !nextChair;
      document.getElementById('seatNextButton').dataset.seatChair = nextChair?.id || '';
    }
  };

  const refresh = async () => {
    try {
      const response = await fetch(`${page.dataset.liveUrl}?date=${encodeURIComponent(dateInput.value)}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) throw new Error('Unable to refresh the chair board.');
      boardData = await response.json();
      page.dataset.date = boardData.date;
      updateMetrics(boardData.metrics);
      updateView();
    } catch (error) {
      console.error(error);
    }
  };

  const seatNext = async (chairId) => {
    if (!chairId) return;
    try {
      const response = await fetch(`${page.dataset.seatUrl}chairs/${encodeURIComponent(chairId)}/seat-next/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to seat the next client.');
      await refresh();
    } catch (error) {
      window.alert(error.message);
    }
  };

  document.querySelectorAll('[data-board-view]').forEach((button) => {
    button.addEventListener('click', () => {
      selectedView = button.dataset.boardView;
      updateView();
    });
  });
  document.getElementById('boardSearch').addEventListener('input', updateView);
  dateInput.addEventListener('change', refresh);
  document.getElementById('todayButton').addEventListener('click', () => {
    dateInput.value = inputDate(new Date());
    refresh();
  });
  document.getElementById('previousDay').addEventListener('click', () => {
    const date = parseDate(dateInput.value);
    date.setDate(date.getDate() - 1);
    dateInput.value = inputDate(date);
    refresh();
  });
  document.getElementById('nextDay').addEventListener('click', () => {
    const date = parseDate(dateInput.value);
    date.setDate(date.getDate() + 1);
    dateInput.value = inputDate(date);
    refresh();
  });

  document.addEventListener('click', async (event) => {
    const seatButton = event.target.closest('[data-seat-chair]');
    if (seatButton) {
      await seatNext(seatButton.dataset.seatChair);
      return;
    }
    const detailButton = event.target.closest('[data-open-detail]');
    if (detailButton) openDetails(detailButton.dataset.openDetail);
  });

  const appointmentDialog = document.getElementById('appointmentDialog');
  const appointmentForm = document.getElementById('appointmentForm');
  document.querySelectorAll('[data-open-appointment]').forEach((button) => {
    button.addEventListener('click', () => {
      const isWalkIn = button.dataset.openAppointment === 'walk_in';
      document.getElementById('appointmentType').value = isWalkIn ? 'walk_in' : 'booking';
      document.getElementById('appointmentDialogTitle').textContent = isWalkIn ? 'Add a walk-in' : 'Create a booking';
      const bookingTime = appointmentForm.elements.start_time;
      document.getElementById('bookingTimeLabel').hidden = isWalkIn;
      bookingTime.required = !isWalkIn;
      if (!isWalkIn && !bookingTime.value) {
        const date = parseDate(dateInput.value);
        date.setHours(12, 0, 0, 0);
        bookingTime.value = `${date.toLocaleDateString('en-CA')}T12:00`;
      }
      appointmentDialog.showModal();
    });
  });
  appointmentForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorMessage = document.getElementById('appointmentError');
    errorMessage.hidden = true;
    try {
      const response = await fetch(page.dataset.createUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
        body: new FormData(appointmentForm),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to save appointment.');
      appointmentDialog.close();
      appointmentForm.reset();
      await refresh();
    } catch (error) {
      errorMessage.textContent = error.message;
      errorMessage.hidden = false;
    }
  });

  document.querySelectorAll('[data-close-dialog]').forEach((button) => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
  document.getElementById('seatNextButton').addEventListener('click', (event) => {
    seatNext(event.currentTarget.dataset.seatChair);
  });

  function openDetails(appointmentId) {
    const appointment = activeAppointments().find((item) => item.id === appointmentId);
    if (!appointment) return;
    document.getElementById('detailClient').textContent = appointment.client;
    document.getElementById('appointmentDetailContent').innerHTML = [
      ['Phone', appointment.phone || 'Not provided'],
      ['Date and time', `${formatDate(dateInput.value)} · ${formatTime(appointment.start_time)}`],
      ['Chair and barber', `${appointment.chair} · ${appointment.barber}`],
      ['Service', appointment.service],
      ['Duration', `${appointment.duration} minutes`],
      ['Price', `KSh ${Number(appointment.price).toLocaleString()}`],
      ['Status', appointment.status_label],
      ['Notes', appointment.notes || 'No notes'],
    ].map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('');
    const actions = document.getElementById('appointmentDetailActions');
    actions.innerHTML = appointment.status === 'IN_CHAIR'
      ? `<a class="salon-primary-action" href="${escapeHtml(page.dataset.saleUrl)}?appointment=${encodeURIComponent(appointment.id)}">Complete sale</a>`
      : '<span class="board-lane-empty">Use the queue to seat this client when ready.</span>';
    document.getElementById('appointmentDetails').showModal();
  }

  const updateTimers = () => {
    document.querySelectorAll('[data-started-at]').forEach((element) => {
      const elapsed = Math.max(0, Math.floor((Date.now() - new Date(element.dataset.startedAt).getTime()) / 60000));
      element.textContent = `In chair · ${elapsed} min`;
    });
  };
  refresh();
  window.setInterval(refresh, 10000);
  window.setInterval(updateTimers, 1000);
});
