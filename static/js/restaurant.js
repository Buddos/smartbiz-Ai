document.addEventListener("DOMContentLoaded", () => {
    const shell = document.querySelector(".restaurant-app-shell");
    const menuButton = document.querySelector("[data-restaurant-menu]");
    if (shell && menuButton) {
        const setOpen = (open) => {
            shell.classList.toggle("is-menu-open", open);
            menuButton.setAttribute("aria-expanded", String(open));
            menuButton.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
        };
        menuButton.addEventListener("click", () => {
            setOpen(!shell.classList.contains("is-menu-open"));
        });
        document.querySelectorAll("[data-restaurant-close]").forEach((button) => {
            button.addEventListener("click", () => setOpen(false));
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") setOpen(false);
        });
    }

    const livePage = document.querySelector("[data-restaurant-refresh]");
    if (livePage) {
        document.querySelectorAll(".restaurant-operations form").forEach((form) => {
            form.addEventListener("input", () => { form.dataset.changed = "true"; });
            form.addEventListener("change", () => { form.dataset.changed = "true"; });
        });
        window.setInterval(() => {
            const hasUnsavedChanges = document.querySelector(
                '.restaurant-operations form[data-changed="true"]',
            );
            if (!document.hidden && !hasUnsavedChanges && !document.querySelector(":focus-within")) {
                window.location.reload();
            }
        }, Number(livePage.dataset.restaurantRefresh));
    }

    const dashboard = document.querySelector("[data-restaurant-live]");
    if (!dashboard) return;

    const currency = dashboard.querySelector("[data-metric='today_revenue']")?.closest("strong")
        ?.textContent.trim().split(/\s+/)[0] || "";
    const formatAmount = (amount) => Number(amount || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });

    const updateRecentOrders = (orders, code) => {
        const tbody = dashboard.querySelector("[data-recent-orders]");
        if (!tbody) return;
        tbody.replaceChildren();
        if (!orders.length) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.className = "restaurant-empty";
            cell.colSpan = 5;
            cell.textContent = "No orders have been recorded today.";
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
            const customer = document.createElement("small");
            customer.textContent = order.customer;
            orderCell.append(link, customer);
            const table = document.createElement("td");
            table.textContent = order.table_reference || "—";
            const time = document.createElement("td");
            time.textContent = order.time;
            const statusCell = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = "restaurant-status";
            badge.textContent = order.status;
            statusCell.append(badge);
            const total = document.createElement("td");
            total.className = "restaurant-number";
            total.textContent = `${code} ${formatAmount(order.total)}`;
            row.append(orderCell, table, time, statusCell, total);
            tbody.append(row);
        });
    };

    const updateList = (selector, records, emptyText, createItem) => {
        const list = dashboard.querySelector(selector);
        if (!list) return;
        list.replaceChildren();
        if (!records.length) {
            const empty = document.createElement("p");
            empty.className = "restaurant-empty";
            empty.textContent = emptyText;
            list.append(empty);
            return;
        }
        records.forEach((record, index) => list.append(createItem(record, index)));
    };

    const liveStatus = dashboard.querySelector(".restaurant-live-bar span:first-child");
    const setLiveStatus = (message) => {
        if (liveStatus) liveStatus.textContent = message;
    };

    const refresh = async () => {
        if (document.hidden) return;
        try {
            const response = await fetch(dashboard.dataset.apiUrl, {
                credentials: "same-origin",
                cache: "no-store",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) throw new Error(`Dashboard refresh failed (${response.status}).`);
            const data = await response.json();
            ["today_revenue", "completed_orders", "open_orders", "average_order", "menu_item_count", "low_stock_count"]
                .forEach((key) => {
                    const element = dashboard.querySelector(`[data-metric="${key}"]`);
                    if (!element) return;
                    element.textContent = key === "today_revenue" || key === "average_order"
                        ? formatAmount(data[key])
                        : Number(data[key] || 0).toLocaleString();
                });
            updateRecentOrders(data.recent_orders, data.currency || currency);
            updateList(
                "[data-top-items]",
                data.top_items,
                "No completed menu sales recorded today.",
                (item, index) => {
                    const row = document.createElement("div");
                    row.className = "restaurant-ranked-item";
                    const rank = document.createElement("span");
                    rank.className = "restaurant-rank";
                    rank.textContent = String(index + 1);
                    const details = document.createElement("div");
                    const name = document.createElement("strong");
                    name.textContent = item.product_name;
                    const units = document.createElement("small");
                    units.textContent = `${item.units} sold`;
                    details.append(name, units);
                    const total = document.createElement("b");
                    total.textContent = `${data.currency} ${formatAmount(item.revenue)}`;
                    row.append(rank, details, total);
                    return row;
                },
            );
            updateList(
                "[data-low-stock-items]",
                data.low_stock_items,
                "No active menu or stock items are at or below their reorder level.",
                (item) => {
                    const row = document.createElement("div");
                    row.className = "restaurant-stock-item";
                    const icon = document.createElement("span");
                    icon.className = "restaurant-stock-warning";
                    const warning = document.createElement("i");
                    warning.className = "fa-solid fa-triangle-exclamation";
                    warning.setAttribute("aria-hidden", "true");
                    icon.append(warning);
                    const name = document.createElement("strong");
                    name.textContent = item.name;
                    const stock = document.createElement("span");
                    stock.textContent = `${item.current_stock} left · reorder at ${item.reorder_level}`;
                    row.append(icon, name, stock);
                    return row;
                },
            );
            const updated = dashboard.querySelector("[data-last-updated]");
            if (updated) updated.textContent = `Updated ${new Date(data.last_updated).toLocaleTimeString()}`;
        } catch (error) {
            const updated = dashboard.querySelector("[data-last-updated]");
            if (updated) updated.textContent = "Live refresh failed; showing the last available data.";
            console.error(error);
        }
    };

    let socket;
    let reconnectDelay = 1000;
    let refreshTimer;
    let reconnectTimer;

    const queueRefresh = () => {
        window.clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(refresh, 200);
    };

    const connect = () => {
        const url = new URL("/ws/v1/business/", window.location.href);
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(url);

        socket.addEventListener("open", () => {
            reconnectDelay = 1000;
            window.clearInterval(fallbackRefresh);
            fallbackRefresh = null;
        });
        socket.addEventListener("message", (event) => {
            let message;
            try {
                message = JSON.parse(event.data);
            } catch (error) {
                console.error("Received an invalid realtime message.", error);
                return;
            }
            if (message.type === "connection.ready") {
                setLiveStatus("Live updates connected");
                queueRefresh();
            } else if (message.type === "business.data.changed") {
                queueRefresh();
            }
        });
        socket.addEventListener("close", () => {
            setLiveStatus("Live updates reconnecting · fallback refresh every 30 seconds");
            window.clearInterval(fallbackRefresh);
            fallbackRefresh = window.setInterval(refresh, 30_000);
            window.clearTimeout(reconnectTimer);
            reconnectTimer = window.setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 30_000);
        });
        socket.addEventListener("error", () => socket.close());
    };

    let fallbackRefresh = window.setInterval(refresh, 30_000);
    connect();

    window.setInterval(() => {
        if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "ping" }));
        } else if (fallbackRefresh === null) {
            fallbackRefresh = window.setInterval(refresh, 30_000);
        }
    }, 25_000);

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) queueRefresh();
    });
});
