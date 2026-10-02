document.querySelectorAll("[data-dashboard-account-menu]").forEach((menu) => {
    const toggle = menu.querySelector("[data-dashboard-account-toggle]");
    const popover = menu.querySelector("[data-dashboard-account-popover]");

    if (!toggle || !popover) return;

    const setOpen = (open) => {
        toggle.setAttribute("aria-expanded", String(open));
        popover.hidden = !open;
    };

    toggle.addEventListener("click", () => setOpen(popover.hidden));
    document.addEventListener("click", (event) => {
        if (!menu.contains(event.target)) setOpen(false);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !popover.hidden) {
            setOpen(false);
            toggle.focus();
        }
    });
});
