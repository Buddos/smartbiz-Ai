document.addEventListener("DOMContentLoaded", () => {
    const shell = document.querySelector(".retail-app-shell");
    const menuButton = document.querySelector("[data-retail-menu]");
    if (shell && menuButton) {
        const setOpen = (open) => {
            shell.classList.toggle("is-menu-open", open);
            menuButton.setAttribute("aria-expanded", String(open));
            menuButton.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
        };
        menuButton.addEventListener("click", () => {
            setOpen(!shell.classList.contains("is-menu-open"));
        });
        document.addEventListener("click", (event) => {
            if (!shell.contains(event.target)) setOpen(false);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") setOpen(false);
        });
    }

    document.querySelectorAll("[data-retail-order-form]").forEach((form) => {
        const lines = form.querySelector("[data-retail-order-lines]");
        const addButton = form.querySelector("[data-add-order-line]");
        const template = form.querySelector("[data-order-empty-form]");
        const totalForms = form.querySelector('input[name="items-TOTAL_FORMS"]');
        if (!lines || !addButton || !template || !totalForms) return;

        addButton.addEventListener("click", () => {
            const index = Number(totalForms.value);
            const markup = template.innerHTML.replaceAll("__prefix__", String(index));
            lines.insertAdjacentHTML("beforeend", markup);
            totalForms.value = String(index + 1);
        });
    });
});
