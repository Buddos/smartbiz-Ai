document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("supplier-form");
    const dialog = document.getElementById("supplierConfirmDialog");
    if (!(form instanceof HTMLFormElement) || !(dialog instanceof HTMLElement)) return;

    const editButton = dialog.querySelector("[data-supplier-edit]");
    const confirmButton = dialog.querySelector("[data-supplier-confirm]");
    const nameInput = form.querySelector('[name="supplier-name"]');
    const phoneInput = form.querySelector('[name="supplier-phone"]');
    const emailInput = form.querySelector('[name="supplier-email"]');
    const confirmName = dialog.querySelector("[data-confirm-name]");
    const confirmPhone = dialog.querySelector("[data-confirm-phone]");
    const confirmEmail = dialog.querySelector("[data-confirm-email]");
    if (
        !(editButton instanceof HTMLButtonElement)
        || !(confirmButton instanceof HTMLButtonElement)
        || !(nameInput instanceof HTMLInputElement)
        || !(phoneInput instanceof HTMLInputElement)
        || !(emailInput instanceof HTMLInputElement)
        || !(confirmName instanceof HTMLElement)
        || !(confirmPhone instanceof HTMLElement)
        || !(confirmEmail instanceof HTMLElement)
    ) return;

    let confirmed = false;

    function closeDialog() {
        dialog.hidden = true;
        document.body.classList.remove("supplier-confirm-open");
    }

    form.addEventListener("submit", (event) => {
        if (confirmed) return;
        event.preventDefault();
        confirmName.textContent = nameInput.value.trim() || "—";
        confirmPhone.textContent = phoneInput.value.trim() || "Not provided";
        confirmEmail.textContent = emailInput.value.trim() || "Not provided";
        dialog.hidden = false;
        document.body.classList.add("supplier-confirm-open");
        editButton.focus();
    });

    editButton.addEventListener("click", () => {
        closeDialog();
        nameInput.focus();
    });

    confirmButton.addEventListener("click", () => {
        confirmed = true;
        confirmButton.disabled = true;
        confirmButton.setAttribute("aria-busy", "true");
        form.requestSubmit();
    });

    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) closeDialog();
    });

    document.addEventListener("keydown", (event) => {
        if (dialog.hidden) return;
        if (event.key === "Escape") {
            closeDialog();
            editButton.focus();
        } else if (event.key === "Tab") {
            const focusable = [editButton, confirmButton].filter((button) => !button.disabled);
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    });
});
