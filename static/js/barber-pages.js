document.addEventListener('DOMContentLoaded', () => {
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[character]));
  const csrf = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1] || '';
  const fetchJson = async (url) => {
    const response = await fetch(url, {cache: 'no-store', headers: {'X-Requested-With': 'XMLHttpRequest'}});
    if (!response.ok) throw new Error(`Live refresh failed (${response.status}).`);
    return response.json();
  };
  const setStatus = (id, message) => {
    const element = document.getElementById(id);
    if (element) element.textContent = message;
  };
  const reportError = (id, error) => {
    console.error(error);
    setStatus(id, 'Live update unavailable. The displayed values are from the last successful refresh.');
  };

  const clientPage = document.getElementById('clientPage');
  if (clientPage) {
    const search = document.getElementById('clientSearch');
    const status = document.getElementById('clientStatus');
    const renderClients = async () => {
      try {
        const params = new URLSearchParams();
        if (search.value.trim()) params.set('search', search.value.trim());
        if (status.value) params.set('status', status.value);
        const data = await fetchJson(`${clientPage.dataset.liveUrl}?${params}`);
        document.getElementById('clientTotal').textContent = `(${data.summary.total})`;
        document.querySelectorAll('[data-client-count]').forEach((element) => {
          element.textContent = data.summary[element.dataset.clientCount] ?? 0;
        });
        const rows = document.getElementById('clientRows');
        rows.innerHTML = data.clients.length ? data.clients.map((client) => `
          <tr class="client-row status-${escapeHtml(client.status)}" data-client-row>
            <td><a class="client-name" href="${escapeHtml(client.url)}">${escapeHtml(client.name)}</a></td>
            <td>${client.phone ? `<a href="tel:${escapeHtml(client.phone)}">${escapeHtml(client.phone)}</a>` : '—'}</td>
            <td>${escapeHtml(client.last_visit)}${client.days_since !== null ? ` · ${escapeHtml(client.days_since)}d ago` : ''}</td>
            <td>${Number(client.visits)}</td>
            <td>KSh ${Number(client.spent).toLocaleString()}</td>
            <td>${escapeHtml(client.barber)}</td>
            <td><span class="client-status-chip ${escapeHtml(client.status)}">${escapeHtml(client.status)}</span></td>
            <td><a class="table-action" href="${escapeHtml(client.url)}">Details</a>${client.phone ? `<a class="table-action" href="tel:${escapeHtml(client.phone)}">Call</a>` : ''}<a class="table-action" href="${escapeHtml(clientPage.dataset.bookUrl)}">Book</a></td>
          </tr>`).join('') : '<tr><td colspan="8" class="table-empty">No clients match this search.</td></tr>';
        setStatus('clientLiveStatus', 'Client information refreshed just now.');
      } catch (error) {
        reportError('clientLiveStatus', error);
      }
    };
    let searchTimer;
    search.addEventListener('input', () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(renderClients, 250);
    });
    status.addEventListener('change', renderClients);
    window.setInterval(renderClients, 30000);
  }

  const goalCards = document.getElementById('goalCards');
  if (goalCards) {
    const refreshGoals = async () => {
      try {
        const data = await fetchJson(goalCards.dataset.liveUrl);
        data.goals.forEach((goal) => {
          const card = goalCards.querySelector(`[data-goal-card="${CSS.escape(goal.id)}"]`);
          if (!card) return;
          const unit = card.dataset.goalUnit || '';
          const format = (value) => `${unit}${Number(value).toLocaleString()}`;
          card.querySelector('.goal-value-line strong').textContent = format(goal.current);
          card.querySelector('.goal-value-line span').textContent = `/ ${format(goal.target)}`;
          const bar = card.querySelector('[data-goal-progress]');
          bar.style.width = `${goal.percent}%`;
          const track = bar.parentElement;
          track.setAttribute('aria-valuenow', String(goal.percent));
          card.querySelector('[data-goal-percent]').textContent = `${goal.percent}%`;
          card.querySelector('.goal-progress-label span:last-child').textContent = goal.hit
            ? 'Target reached'
            : `${format(goal.remaining)} to go`;
          card.querySelector('[data-goal-tip]').textContent = goal.hit
            ? 'You reached this target. Great work.'
            : 'Keep going — progress reflects recorded business activity.';
        });
        const streakRow = document.querySelector('[data-live-streak]');
        if (streakRow) {
          document.getElementById('streakMessage').hidden = data.daily_streak === 0;
          document.getElementById('streakEmpty').hidden = data.daily_streak !== 0;
          streakRow.textContent = data.daily_streak
            ? `${data.daily_streak} day${data.daily_streak === 1 ? '' : 's'} · Daily revenue target reached on consecutive days`
            : '';
        }
        setStatus('goalLiveStatus', 'Goal progress refreshed just now.');
      } catch (error) {
        reportError('goalLiveStatus', error);
      }
    };
    window.setInterval(refreshGoals, 30000);
  }

  const moneyPage = document.getElementById('moneyPage');
  if (moneyPage) {
    const customDates = document.getElementById('customMoneyDates');
    let period = new URLSearchParams(window.location.search).get('period') || 'month';
    let customRange = null;
    const format = (value) => Number(value || 0).toLocaleString();
    const refreshMoney = async () => {
      if (period === 'custom' && !customRange) return;
      try {
        const params = new URLSearchParams({period});
        if (period === 'custom' && customRange) {
          params.set('start', customRange.start);
          params.set('end', customRange.end);
        }
        const data = await fetchJson(`${moneyPage.dataset.liveUrl}?${params}`);
        ['revenue', 'expenses', 'profit', 'product_cost', 'cash_in', 'cash_out', 'margin'].forEach((key) => {
          document.querySelectorAll(`[data-money="${key}"]`).forEach((element) => {
            element.textContent = format(data[key]);
          });
        });
        document.getElementById('moneyPeriodLabel').textContent = `${data.start} – ${data.end}`;
        const revenueChange = document.querySelector('[data-money-change="revenue"]');
        const expenseChange = document.querySelector('[data-money-change="expenses"]');
        if (revenueChange) revenueChange.textContent = data.revenue_change === null ? 'No prior-period comparison' : `${data.revenue_change}% vs prior period`;
        if (expenseChange) expenseChange.textContent = data.expense_change === null ? 'No prior-period comparison' : `${data.expense_change}% vs prior period`;
        document.getElementById('moneySources').innerHTML = data.sources.map((item) => `
          <div class="money-source-row"><div><strong>${escapeHtml(item.name)}</strong><span>KSh ${format(item.amount)} · ${Number(item.percent)}%</span></div><i><b style="width:${Math.min(100, Number(item.percent))}%"></b></i></div>`).join('')
          || '<p class="table-empty">No sales recorded in this period.</p>';
        const peak = Math.max(1, ...data.trend.flatMap((day) => [Number(day.revenue), Number(day.expenses)]));
        document.getElementById('moneyTrend').innerHTML = data.trend.map((day) => `
          <div class="money-trend-row"><span>${escapeHtml(day.date)}</span><div><i class="trend-revenue" style="width:${Number(day.revenue) / peak * 100}%"></i><i class="trend-expense" style="width:${Number(day.expenses) / peak * 100}%"></i></div><strong>KSh ${format(day.revenue)}</strong></div>`).join('')
          || '<p class="table-empty">No daily totals yet.</p>';
        document.getElementById('expenseBreakdown').innerHTML = data.expense_breakdown.map((item) => `<div><span>${escapeHtml(item.name)}</span><strong>KSh ${format(item.amount)}</strong></div>`).join('')
          || '<p class="table-empty">No expenses recorded in this period.</p>';
        document.getElementById('expenseAlerts').innerHTML = data.expense_alerts.length
          ? data.expense_alerts.map((item) => `<p><strong>${escapeHtml(item.name)} expenses increased ${Number(item.percent)}%</strong> · KSh ${format(item.amount)} more than the comparable prior period.</p>`).join('')
          : '<p>No expense category has increased by more than 15% versus the comparable prior period.</p>';
        document.getElementById('cashDays').innerHTML = data.cash_days.map((day) => `<tr><td>${escapeHtml(day.date)}</td><td>KSh ${format(day.in)}</td><td>KSh ${format(day.out)}</td><td>KSh ${format(day.net)}</td></tr>`).join('');
        setStatus('moneyLiveStatus', 'Money figures refreshed just now.');
      } catch (error) {
        reportError('moneyLiveStatus', error);
      }
    };
    moneyPage.querySelectorAll('[data-period]').forEach((button) => button.addEventListener('click', () => {
      period = button.dataset.period;
      customDates.hidden = period !== 'custom';
      moneyPage.querySelectorAll('[data-period]').forEach((item) => item.classList.toggle('is-active', item === button));
      if (period === 'custom') {
        customRange = {start: document.getElementById('moneyStart').value, end: document.getElementById('moneyEnd').value};
        refreshMoney();
      } else refreshMoney();
    }));
    document.getElementById('applyMoneyDates').addEventListener('click', () => {
      customRange = {start: document.getElementById('moneyStart').value, end: document.getElementById('moneyEnd').value};
      if (!customRange.start || !customRange.end || customRange.end < customRange.start) {
        document.getElementById('moneyPeriodLabel').textContent = 'Choose a valid date range.';
        return;
      }
      refreshMoney();
    });
    window.setInterval(refreshMoney, 30000);
  }

  const schedulePage = document.getElementById('schedulePage');
  if (schedulePage) {
    const deletePrefix = schedulePage.dataset.deleteUrlPrefix;
    const renderSchedule = async () => {
      try {
        const data = await fetchJson(`${schedulePage.dataset.liveUrl}?week=${encodeURIComponent(schedulePage.dataset.week)}`);
        const byCell = new Map();
        data.shifts.forEach((shift) => {
          const key = `${shift.chair_id}:${shift.date}`;
          byCell.set(key, [...(byCell.get(key) || []), shift]);
        });
        const body = document.getElementById('scheduleGrid');
        body.innerHTML = data.chairs.length ? data.chairs.map((chair) => `
          <tr><th scope="row">${escapeHtml(chair.label)}</th>${data.days.map((day) => {
            const shifts = byCell.get(`${chair.id}:${day.date}`) || [];
            return `<td>${shifts.length ? shifts.map((shift) => `
              <div class="schedule-shift ${shift.day_off ? 'day-off' : ''}">
                <strong>${escapeHtml(shift.barber)}</strong>
                <span>${shift.day_off ? 'Day off' : `${escapeHtml(shift.start)}–${escapeHtml(shift.end)}`}</span>
                ${csrf ? `<form method="post" action="${deletePrefix}${escapeHtml(shift.id)}/delete/"><input type="hidden" name="csrfmiddlewaretoken" value="${escapeHtml(csrf)}"><button type="submit" aria-label="Remove shift">Remove</button></form>` : ''}
              </div>`).join('') : '<span class="schedule-empty-cell">Unstaffed</span>'}</td>`;
          }).join('')}</tr>`).join('') : `<tr><td colspan="8" class="table-empty">Add an active chair to start scheduling.</td></tr>`;
        Object.entries(data.snapshot).forEach(([key, value]) => {
          const element = document.querySelector(`[data-snapshot="${key}"]`);
          if (element) element.textContent = value;
        });
        document.getElementById('chairUtilization').innerHTML = data.utilization.map((chair) => `
          <div class="chair-util-row"><strong>${escapeHtml(chair.chair)}</strong><div class="chair-util-track"><i style="width:${chair.percent}%"></i></div><span>${chair.booked_hours}h booked / ${chair.scheduled_hours}h scheduled</span></div>`).join('')
          || '<p class="table-empty">No scheduled chairs this week.</p>';
      } catch (error) {
        reportError('scheduleLiveStatus', error);
      }
    };
    renderSchedule();
    window.setInterval(renderSchedule, 30000);
  }
});
