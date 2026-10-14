(() => {
    const assistantOrigin = "https://heartful-design-ai.lovable.app";
    const frames = Array.from(document.querySelectorAll("[data-smartbiz-assistant-frame]"));
    if (!frames.length) return;

    const endpoints = {
        me: "/api/users/me/",
        dashboard: "/analytics/api/dashboard-data/",
        salesStats: "/sales/api/stats/",
        inventoryStats: "/inventory/api/stats/",
        restaurant: "/analytics/api/restaurant-dashboard/",
        barberProducts: "/products/api/live-barber-products/",
        barberBoard: "/dashboard/barber/api/live-board/",
        barberClients: "/dashboard/barber/clients/live/",
        barberMoney: "/dashboard/barber/money/live/",
        barberGoals: "/dashboard/barber/goals/live/",
    };

    const pushInProgress = new WeakSet();
    const readyFrames = new WeakSet();

    async function getJson(path) {
        const response = await fetch(path, {
            credentials: "same-origin",
            cache: "no-store",
            headers: { Accept: "application/json" },
        });
        if (!response.ok) {
            if (response.status !== 403 && response.status !== 404) {
                console.error(`SmartBiz assistant data request failed (${response.status}): ${path}`);
            }
            return null;
        }
        if (!(response.headers.get("content-type") || "").includes("application/json")) {
            console.error(`SmartBiz assistant data request returned a non-JSON response: ${path}`);
            return null;
        }
        return response.json();
    }

    async function pushDashboardData(frame) {
        if (
            document.hidden
            || !readyFrames.has(frame)
            || pushInProgress.has(frame)
            || !frame.contentWindow
        ) return;
        pushInProgress.add(frame);
        try {
            const entries = await Promise.all(
                Object.entries(endpoints).map(async ([key, path]) => {
                    try {
                        const value = await getJson(path);
                        return value === null ? null : [key, value];
                    } catch (error) {
                        console.error(`SmartBiz assistant data request failed: ${path}`, error);
                        return null;
                    }
                }),
            );
            const data = Object.fromEntries(entries.filter(Boolean));
            frame.contentWindow.postMessage({ type: "smartbiz:data", data }, assistantOrigin);
        } finally {
            pushInProgress.delete(frame);
        }
    }

    window.addEventListener("message", (event) => {
        const frame = frames.find((candidate) => candidate.contentWindow === event.source);
        if (
            event.origin === assistantOrigin
            && frame
            && event.data?.type === "smartbiz:ready"
        ) {
            readyFrames.add(frame);
            pushDashboardData(frame);
        }
    });

    frames.forEach((frame) => frame.addEventListener("load", () => pushDashboardData(frame)));
    window.setInterval(() => frames.forEach((frame) => pushDashboardData(frame)), 30000);
})();
