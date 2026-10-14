(() => {
    const shell = document.querySelector("[data-hardware-shell]");
    const menuButton = document.querySelector("[data-hardware-menu]");
    const closeMenu = () => {
        shell?.classList.remove("is-menu-open");
        menuButton?.setAttribute("aria-expanded", "false");
    };
    menuButton?.addEventListener("click", () => {
        const isOpen = shell.classList.toggle("is-menu-open");
        menuButton.setAttribute("aria-expanded", String(isOpen));
    });
    document.querySelector("[data-hardware-close]")?.addEventListener("click", closeMenu);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeMenu();
    });

    const liveSurfaces = document.querySelectorAll("[data-hardware-live]");
    if (!liveSurfaces.length) return;

    const statuses = document.querySelectorAll("[data-live-status]");
    const setStatus = (message, state) => {
        statuses.forEach((status) => {
            status.textContent = message;
            status.classList.toggle("is-live", state === "live");
            status.classList.toggle("is-offline", state === "offline");
        });
    };

    const isDashboard = Array.from(liveSurfaces).some((surface) => surface.dataset.hardwareLive === "dashboard");
    const stockNote = document.querySelector("[data-stock-update-note]");
    let retryDelay = 1000;
    let socket;
    let reloadTimer;

    const reloadDashboard = () => {
        if (reloadTimer) return;
        reloadTimer = window.setTimeout(() => window.location.reload(), 350);
    };

    const connect = () => {
        const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(`${scheme}//${window.location.host}/ws/v1/business/`);
        socket.addEventListener("open", () => {
            retryDelay = 1000;
            setStatus("Live · connected", "live");
        });
        socket.addEventListener("message", (event) => {
            let message;
            try {
                message = JSON.parse(event.data);
            } catch (error) {
                setStatus("Live update received in an unreadable format", "offline");
                return;
            }
            if (message.type !== "business.data.changed") return;
            setStatus("Live · just updated", "live");
            if (isDashboard) {
                reloadDashboard();
            } else if (stockNote && ["inventory", "menu", "sales"].includes(message.resource)) {
                stockNote.hidden = false;
            }
        });
        socket.addEventListener("error", () => {
            setStatus("Live connection interrupted · retrying", "offline");
        });
        socket.addEventListener("close", () => {
            setStatus("Reconnecting to live updates…", "offline");
            window.setTimeout(connect, retryDelay);
            retryDelay = Math.min(retryDelay * 2, 30000);
        });
    };

    document.querySelector("[data-refresh-stock]")?.addEventListener("click", () => {
        window.location.reload();
    });
    window.setInterval(() => {
        if (isDashboard && document.visibilityState === "visible" && socket?.readyState !== WebSocket.OPEN) {
            reloadDashboard();
        }
    }, 30000);
    connect();
})();
