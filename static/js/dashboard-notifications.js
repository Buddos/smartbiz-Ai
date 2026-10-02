document.querySelectorAll("[data-notifications]").forEach((container) => {
    const toggle = container.querySelector("[data-notifications-toggle]");
    const panel = container.querySelector("[data-notifications-panel]");
    const close = container.querySelector("[data-notifications-close]");

    if (!toggle || !panel) return;

    const setOpen = (open) => {
        toggle.setAttribute("aria-expanded", String(open));
        panel.hidden = !open;
    };

    toggle.addEventListener("click", () => {
        setOpen(panel.hidden);
    });
    close?.addEventListener("click", () => setOpen(false));
    document.addEventListener("click", (event) => {
        if (!container.contains(event.target)) setOpen(false);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !panel.hidden) {
            setOpen(false);
            toggle.focus();
        }
    });
});
