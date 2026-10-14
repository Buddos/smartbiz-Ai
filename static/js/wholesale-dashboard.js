document.addEventListener("DOMContentLoaded", () => {
    const shell = document.querySelector(".wholesale-shell");
    const menuButton = document.querySelector("[data-toggle-menu]");
    const setMenuOpen = (open) => {
        if (!shell || !menuButton) return;
        shell.classList.toggle("is-menu-open", open);
        menuButton.setAttribute("aria-expanded", String(open));
        menuButton.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    };
    menuButton?.addEventListener("click", () => {
        setMenuOpen(!shell?.classList.contains("is-menu-open"));
    });
    document.querySelector("[data-close-menu]")?.addEventListener("click", () => setMenuOpen(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setMenuOpen(false);
    });

    const dashboard = document.querySelector("[data-wholesale-dashboard]");
    if (!dashboard) return;

    const currency = dashboard.querySelector("[data-metric='today_sales']")
        ?.closest("strong")?.querySelector("small")?.textContent.trim() || "";
    const formatNumber = (value, fractionDigits = 0) => Number(value || 0).toLocaleString(undefined, {
        minimumFractionDigits: fractionDigits,
        maximumFractionDigits: fractionDigits,
    });
    const setMetric = (key, value, money = false) => {
        dashboard.querySelectorAll(`[data-metric="${key}"]`).forEach((element) => {
            element.textContent = formatNumber(value, money ? 2 : 0);
        });
    };
    const setLiveState = (error = false) => {
        const live = dashboard.querySelector(".wholesale-live-state");
        const status = dashboard.querySelector("[data-live-status]");
        live?.classList.toggle("is-error", error);
        if (status) status.textContent = error ? "Refresh delayed" : "Live";
    };
    const setUpdated = (value) => {
        const updated = dashboard.querySelector("[data-last-updated]");
        if (updated && value) {
            updated.textContent = `Updated ${new Date(value).toLocaleTimeString()}`;
        }
    };
    const renderTrend = (trend = []) => {
        const line = dashboard.querySelector("[data-trend-line]");
        const fill = dashboard.querySelector("[data-trend-fill]");
        if (!line || !fill || !trend.length) return;
        const values = trend.map((point) => Number(point.revenue) || 0);
        const max = Math.max(...values, 0);
        const points = values.map((value, index) => {
            const x = values.length < 2 ? 300 : index * 600 / (values.length - 1);
            const y = 145 - (max > 0 ? value / max * 125 : 0);
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        });
        line.setAttribute("points", points.join(" "));
        fill.setAttribute("points", `0,150 ${points.join(" ")} 600,150`);
        const labels = dashboard.querySelector(".wholesale-trend-labels");
        if (labels) {
            const positions = [0, Math.floor((trend.length - 1) / 2), trend.length - 1];
            labels.replaceChildren(...positions.map((index) => {
                const label = document.createElement("span");
                label.textContent = trend[index]?.label || "";
                return label;
            }));
        }
    };
    const renderCustomers = (customers = []) => {
        const list = dashboard.querySelector("[data-top-customers]");
        if (!list) return;
        list.replaceChildren();
        if (!customers.length) {
            const empty = document.createElement("p");
            empty.className = "wholesale-empty";
            empty.textContent = "No customer sales recorded this week.";
            list.append(empty);
            return;
        }
        customers.forEach((customer, index) => {
            const row = document.createElement("div");
            row.className = "wholesale-ranked-row";
            const rank = document.createElement("span");
            rank.className = "wholesale-rank";
            rank.textContent = String(index + 1);
            const name = document.createElement("strong");
            name.textContent = customer.customer__name;
            const total = document.createElement("b");
            total.textContent = `${currency} ${formatNumber(customer.revenue, 2)}`;
            row.append(rank, name, total);
            list.append(row);
        });
    };
    const renderOrders = (orders = []) => {
        const tbody = dashboard.querySelector("[data-recent-orders]");
        if (!tbody) return;
        tbody.replaceChildren();
        if (!orders.length) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.className = "wholesale-empty";
            cell.colSpan = 4;
            cell.textContent = "No orders have been recorded yet.";
            row.append(cell);
            tbody.append(row);
            return;
        }
        orders.forEach((order) => {
            const row = document.createElement("tr");
            const orderCell = document.createElement("td");
            const link = document.createElement("a");
            link.href = order.url;
            link.textContent = order.number;
            orderCell.append(link);
            const customer = document.createElement("td");
            customer.textContent = order.customer;
            const statusCell = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = `wholesale-status is-${order.status_code}`;
            badge.textContent = order.status;
            statusCell.append(badge);
            const total = document.createElement("td");
            total.textContent = `${currency} ${formatNumber(order.total, 2)}`;
            row.append(orderCell, customer, statusCell, total);
            tbody.append(row);
        });
    };
    const renderAging = (buckets = []) => {
        const rows = dashboard.querySelectorAll(".wholesale-aging-row");
        const maximum = Math.max(...buckets.map((bucket) => Number(bucket.amount) || 0), 0);
        buckets.forEach((bucket, index) => {
            const row = rows[index];
            if (!row) return;
            const total = row.querySelector("div:first-child strong");
            const customers = row.querySelector("small");
            const bar = row.querySelector("[data-aging-bar]");
            if (total) total.textContent = `${currency} ${formatNumber(bucket.amount, 2)}`;
            if (customers) customers.textContent = `${formatNumber(bucket.customers)} customers · invoice age`;
            if (bar) bar.style.width = `${maximum ? Number(bucket.amount) / maximum * 100 : 0}%`;
        });
    };
    const renderLowStock = (products = []) => {
        const list = dashboard.querySelector("[data-low-stock]");
        if (!list) return;
        list.replaceChildren();
        if (!products.length) {
            const empty = document.createElement("p");
            empty.className = "wholesale-empty";
            empty.textContent = "No active products are at or below their reorder level.";
            list.append(empty);
            return;
        }
        products.forEach((product) => {
            const row = document.createElement("div");
            const icon = document.createElement("span");
            icon.className = "wholesale-stock-warning";
            const warning = document.createElement("i");
            warning.className = "fas fa-triangle-exclamation";
            warning.setAttribute("aria-hidden", "true");
            icon.append(warning);
            const name = document.createElement("strong");
            name.textContent = product.name;
            const stock = document.createElement("small");
            stock.textContent = `${product.current_stock} left · reorder at ${product.reorder_level}`;
            row.append(icon, name, stock);
            list.append(row);
        });
    };
    let refreshInProgress = false;
    const refresh = async () => {
        if (document.hidden || refreshInProgress) return;
        refreshInProgress = true;
        try {
            const response = await fetch(dashboard.dataset.apiUrl, {
                credentials: "same-origin",
                cache: "no-store",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) throw new Error(`Dashboard refresh failed (${response.status}).`);
            const data = await response.json();
            setMetric("today_sales", data.today_sales, true);
            [
                "orders_today",
                "delivered_today",
                "outstanding_ar",
                "overdue_ar",
                "overdue_customers",
                "pending_orders",
                "out_for_delivery",
                "low_stock_skus",
                "stock_value",
            ].forEach((key) => {
                setMetric(key, data[key], key === "outstanding_ar" || key === "overdue_ar" || key === "stock_value");
            });
            renderTrend(data.sales_trend);
            renderCustomers(data.top_customers);
            renderOrders(data.recent_orders);
            renderAging(data.ar_aging);
            renderLowStock(data.low_stock_items);
            setUpdated(data.last_updated);
            setLiveState();
        } catch (error) {
            console.error("Wholesale dashboard refresh failed.", error);
            setLiveState(true);
        } finally {
            refreshInProgress = false;
        }
    };

    renderTrend([]);
    refresh();
    window.setInterval(refresh, Number(dashboard.dataset.refreshMs) || 30000);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) refresh();
    });
});
