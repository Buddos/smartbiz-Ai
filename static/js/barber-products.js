document.addEventListener('DOMContentLoaded', () => {
  const page = document.getElementById('barberProductsPage');
  const productRows = document.getElementById('productRows');
  const searchField = document.getElementById('productSearch');
  const categoryField = document.getElementById('productCategory');
  const statusField = document.getElementById('productStatus');
  if (!page || !productRows || !searchField || !categoryField || !statusField) return;

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[character]));
  const csrf = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1];
  let products = [];
  let selectedProduct = null;
  let refreshBusy = false;

  const queryString = () => {
    const params = new URLSearchParams();
    if (searchField.value.trim()) params.set('search', searchField.value.trim());
    if (categoryField.value) params.set('category', categoryField.value);
    if (statusField.value) params.set('status', statusField.value);
    return params.toString();
  };

  const renderRows = () => {
    productRows.innerHTML = products.map((product) => {
      const stateLabel = {
        healthy: 'In stock', low: 'Low stock', out: 'Out of stock', archived: 'Archived',
      }[product.state] || product.state;
      return `<tr class="product-row is-${escapeHtml(product.state)}" data-product-row="${escapeHtml(product.id)}">
        <td data-label="Select"><input type="checkbox" class="product-select" value="${escapeHtml(product.id)}" aria-label="Select ${escapeHtml(product.name)}"></td>
        <td data-label="Product"><button type="button" class="product-name-button" data-open-product="${escapeHtml(product.id)}">${escapeHtml(product.name)}</button><span class="product-sku">${escapeHtml(product.sku)}</span></td>
        <td data-label="Category">${escapeHtml(product.category)}</td>
        <td data-label="Stock">${Number(product.stock)} units</td>
        <td data-label="Reorder">${Number(product.reorder)}</td>
        <td data-label="Cost">KSh ${Number(product.cost).toLocaleString()}</td>
        <td data-label="Price">KSh ${Number(product.price).toLocaleString()}</td>
        <td data-label="Margin">${Number(product.margin)}%</td>
        <td data-label="Sold · 30d">${Number(product.sold_30d)}</td>
        <td data-label="Status"><span class="stock-status ${escapeHtml(product.state)}">${escapeHtml(stateLabel)}</span></td>
        <td data-label="Actions"><div class="row-actions">
          <button type="button" class="row-action" data-restock="${escapeHtml(product.id)}">Restock</button>
          <button type="button" class="row-action" data-edit-product="${escapeHtml(product.id)}">Edit</button>
          ${product.active ? `<button type="button" class="row-action" data-archive="${escapeHtml(product.id)}">Archive</button>` : ''}
        </div></td>
      </tr>`;
    }).join('');
    const empty = document.getElementById('productEmpty');
    empty.hidden = products.length > 0;
    if (!products.length) {
      empty.textContent = searchField.value || categoryField.value || statusField.value
        ? 'No products match these filters.'
        : 'No products yet. Add retail products such as pomade, beard oil or shampoo to start tracking sales.';
    }
    updateBulkBar();
  };

  const renderAlerts = (alerts) => {
    const container = document.getElementById('lowStockAlerts');
    document.getElementById('lowStockCount').textContent = `(${alerts.length})`;
    container.innerHTML = alerts.length ? alerts.map((item) => `
      <div class="stock-alert-item">
        <div><strong>${escapeHtml(item.name)}</strong><br><span>${Number(item.stock)} units · reorder at ${Number(item.reorder)}</span></div>
        <button class="row-action" type="button" data-restock="${escapeHtml(item.id)}">Restock</button>
      </div>`).join('') : '<p class="product-live-note">All active products are above their reorder levels.</p>';
  };

  const renderBarberRates = (rates) => {
    const container = document.getElementById('barberAttachRates');
    const maxRate = Math.max(1, ...rates.map((item) => Number(item.rate)));
    container.innerHTML = rates.length ? rates.map((item) => `
      <div class="attach-row">
        <strong>${escapeHtml(item.name)}</strong>
        <div class="attach-track" role="img" aria-label="${escapeHtml(item.rate)} percent attach rate"><i style="width:${Math.min(100, Number(item.rate) / maxRate * 100)}%"></i></div>
        <span>${Number(item.rate)}%</span>
      </div>`).join('') : '<p class="product-live-note">No barber visit data yet.</p>';
  };

  const renderMetrics = (metrics) => {
    document.querySelectorAll('[data-product-metric]').forEach((element) => {
      const key = element.dataset.productMetric;
      const value = metrics[key] ?? 0;
      element.textContent = ['revenue'].includes(key) ? Number(value).toLocaleString() : value;
    });
    document.getElementById('productCount').textContent = `(${metrics.total_products || 0})`;
  };

  const renderDrawer = (product) => {
    selectedProduct = product;
    document.getElementById('drawerProductName').textContent = product.name;
    document.getElementById('drawerProductStats').innerHTML = [
      ['Category', product.category],
      ['Status', product.state === 'healthy' ? 'In stock' : product.state.replace('-', ' ')],
      ['Current stock', `${product.stock} units`],
      ['Reorder at', `${product.reorder} units`],
      ['Cost', `KSh ${Number(product.cost).toLocaleString()}`],
      ['Price', `KSh ${Number(product.price).toLocaleString()}`],
      ['Margin', `${product.margin}%`],
      ['Sold in last 30 days', `${product.sold_30d} units`],
      ['Retail revenue · 30 days', `KSh ${Number(product.revenue_30d).toLocaleString()}`],
      ['Estimated gross profit · 30 days', `KSh ${Math.round(product.profit_30d).toLocaleString()}`],
    ].map(([label, value]) => `<div class="drawer-stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('');
    const drawer = document.getElementById('productDrawer');
    drawer.hidden = false;
    drawer.setAttribute('aria-hidden', 'false');
    document.getElementById('productDrawerBackdrop').hidden = false;
    requestAnimationFrame(() => drawer.classList.add('is-open'));
  };

  const closeDrawer = () => {
    const drawer = document.getElementById('productDrawer');
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    document.getElementById('productDrawerBackdrop').hidden = true;
    window.setTimeout(() => { drawer.hidden = true; }, 200);
  };

  const updateBulkBar = () => {
    const selected = productRows.querySelectorAll('.product-select:checked');
    document.getElementById('selectedCount').textContent = selected.length;
    document.getElementById('bulkBar').hidden = selected.length === 0;
  };

  const openProductForm = (product = null) => {
    const form = document.getElementById('productForm');
    form.reset();
    document.getElementById('productId').value = product?.id || '';
    document.getElementById('productModalTitle').textContent = product ? 'Edit product' : 'Add product';
    if (product) {
      const values = {
        name: product.name,
        sku: product.sku,
        purchase_price: product.cost,
        selling_price: product.price,
        current_stock: product.stock,
        reorder_level: product.reorder,
        category: product.category_id || '',
        is_active: product.active,
      };
      Object.entries(values).forEach(([name, value]) => {
        const field = form.elements.namedItem(name);
        if (!field) return;
        if (field.type === 'checkbox') field.checked = Boolean(value);
        else field.value = value;
      });
    } else {
      const activeField = form.elements.namedItem('is_active');
      if (activeField) activeField.checked = true;
    }
    document.getElementById('productModal').showModal();
  };

  const productAction = async (productId, action, quantity) => {
    const url = page.dataset.actionUrl.replace('__product_id__', encodeURIComponent(productId));
    const body = new URLSearchParams({ action });
    if (quantity !== undefined) body.set('quantity', String(quantity));
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to update product.');
  };

  const restockProduct = async (productId) => {
    const rawQuantity = window.prompt('How many units are being added?');
    if (rawQuantity === null) return;
    const quantity = Number(rawQuantity);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      window.alert('Enter a whole number greater than zero.');
      return;
    }
    try {
      await productAction(productId, 'restock', quantity);
      await refresh();
    } catch (error) {
      window.alert(error.message);
    }
  };

  const refresh = async () => {
    if (refreshBusy || document.getElementById('productModal').open) return;
    refreshBusy = true;
    try {
      const query = queryString();
      const response = await fetch(`${page.dataset.liveUrl}${query ? `?${query}` : ''}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) throw new Error('Unable to refresh product data.');
      const data = await response.json();
      products = data.products;
      renderMetrics(data.metrics);
      renderRows();
      renderAlerts(data.low_stock);
      renderBarberRates(data.barber_rates);
      document.getElementById('productUpdatedAt').textContent = `Updated ${new Date(data.last_updated).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })} · automatic refresh every 15 seconds`;
      if (selectedProduct) {
        const latest = products.find((product) => product.id === selectedProduct.id);
        if (latest) renderDrawer(latest);
      }
    } catch (error) {
      console.error(error);
    } finally {
      refreshBusy = false;
    }
  };

  document.getElementById('addProductButton').addEventListener('click', () => openProductForm());
  document.getElementById('closeProductModal').addEventListener('click', () => document.getElementById('productModal').close());
  document.getElementById('cancelProductForm').addEventListener('click', () => document.getElementById('productModal').close());
  document.getElementById('closeProductDrawer').addEventListener('click', closeDrawer);
  document.getElementById('productDrawerBackdrop').addEventListener('click', closeDrawer);
  document.getElementById('drawerRestock').addEventListener('click', () => {
    if (selectedProduct) restockProduct(selectedProduct.id);
  });
  document.getElementById('drawerEdit').addEventListener('click', () => {
    if (selectedProduct) openProductForm(selectedProduct);
  });
  document.getElementById('clearProductFilters').addEventListener('click', () => {
    searchField.value = '';
    categoryField.value = '';
    statusField.value = '';
    refresh();
  });

  let searchTimer;
  searchField.addEventListener('input', () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(refresh, 250);
  });
  categoryField.addEventListener('change', refresh);
  statusField.addEventListener('change', refresh);
  document.getElementById('selectAllProducts').addEventListener('change', (event) => {
    productRows.querySelectorAll('.product-select').forEach((checkbox) => { checkbox.checked = event.target.checked; });
    updateBulkBar();
  });
  productRows.addEventListener('change', (event) => {
    if (event.target.matches('.product-select')) updateBulkBar();
  });
  document.addEventListener('click', async (event) => {
    const openButton = event.target.closest('[data-open-product]');
    if (openButton) {
      const product = products.find((item) => item.id === openButton.dataset.openProduct);
      if (product) renderDrawer(product);
      return;
    }
    const editButton = event.target.closest('[data-edit-product]');
    if (editButton) {
      const product = products.find((item) => item.id === editButton.dataset.editProduct);
      if (product) openProductForm(product);
      return;
    }
    const restockButton = event.target.closest('[data-restock]');
    if (restockButton) {
      await restockProduct(restockButton.dataset.restock);
      return;
    }
    const archiveButton = event.target.closest('[data-archive]');
    if (archiveButton && window.confirm('Archive this product? It will no longer appear in active inventory.')) {
      try {
        await productAction(archiveButton.dataset.archive, 'archive');
        closeDrawer();
        await refresh();
      } catch (error) {
        window.alert(error.message);
      }
    }
  });

  document.querySelectorAll('[data-bulk-action]').forEach((button) => {
    button.addEventListener('click', async () => {
      const selectedIds = Array.from(productRows.querySelectorAll('.product-select:checked'), (item) => item.value);
      const action = button.dataset.bulkAction;
      let quantity;
      if (action === 'restock') {
        quantity = Number(window.prompt('How many units should be added to each selected product?'));
        if (!Number.isInteger(quantity) || quantity <= 0) return;
      } else if (!window.confirm(`Archive ${selectedIds.length} selected products?`)) {
        return;
      }
      try {
        for (const productId of selectedIds) await productAction(productId, action, quantity);
        await refresh();
      } catch (error) {
        window.alert(error.message);
      }
    });
  });

  if (document.getElementById('productId').value) {
    document.getElementById('productModalTitle').textContent = 'Edit product';
    document.getElementById('productModal').showModal();
  }
  refresh();
  window.setInterval(refresh, 15000);
});
