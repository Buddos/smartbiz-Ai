(() => {
    const widget = document.querySelector("[data-assistant-widget]");
    if (!widget) return;

    const toggle = widget.querySelector("[data-assistant-widget-toggle]");
    const panel = widget.querySelector("[data-assistant-widget-panel]");
    const close = widget.querySelector("[data-assistant-widget-close]");
    const frame = widget.querySelector("[data-smartbiz-assistant-frame]");

    function setOpen(open) {
        panel.hidden = !open;
        toggle.setAttribute("aria-expanded", String(open));

        if (open && !frame.src) {
            frame.src = frame.dataset.src;
        }
    }

    toggle.addEventListener("click", () => setOpen(panel.hidden));
    close.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !panel.hidden) {
            setOpen(false);
            toggle.focus();
        }
    });
})();
