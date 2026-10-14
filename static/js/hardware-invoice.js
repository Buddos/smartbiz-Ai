(() => {
    const form = document.querySelector("#hardwareInvoiceForm");
    if (!form) return;

    const rows = document.querySelector("#hardwareInvoiceItems");
    const template = document.querySelector("#hardwareInvoiceItemTemplate");
    const totalForms = document.querySelector("#id_sale_items-TOTAL_FORMS");
    const addButton = document.querySelector("#hardwareInvoiceAddItem");
    const currency = form.dataset.currency || "";
    const priceByProduct = new Map(
        Array.from(document.querySelectorAll("#hardwareInvoiceProducts option"))
            .filter((option) => option.dataset.price)
            .map((option) => [option.value.trim().toLowerCase(), Number(option.dataset.price)])
    );

    const money = (amount) => `${currency} ${amount.toFixed(2)}`;
    const activeRows = () => Array.from(rows.querySelectorAll("[data-invoice-item]"))
        .filter((row) => !row.hidden);

    const recalculate = () => {
        let subtotal = 0;
        activeRows().forEach((row) => {
            const quantity = Number(row.querySelector('input[name$="-quantity"]').value) || 0;
            const unitPrice = Number(row.querySelector('input[name$="-unit_price"]').value) || 0;
            const lineTotal = quantity * unitPrice;
            subtotal += lineTotal;
            row.querySelector("[data-invoice-line-total]").textContent = money(lineTotal);
        });
        const discount = Math.max(0, Number(form.querySelector('[name="discount"]').value) || 0);
        const total = Math.max(0, subtotal - discount);
        document.querySelector("#hardwareInvoiceSubtotal").textContent = money(subtotal);
        document.querySelector("#hardwareInvoiceTotal").textContent = money(total);
        document.querySelector("#hardwareInvoiceSubmitTotal").textContent = money(total);
    };

    const appendRow = () => {
        const index = Number.parseInt(totalForms.value, 10);
        rows.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", String(index)));
        totalForms.value = String(index + 1);
        return rows.lastElementChild;
    };

    const removeRow = (row) => {
        const deleteInput = row.querySelector('input[name$="-DELETE"]');
        if (activeRows().length === 1) {
            row.querySelectorAll("input").forEach((input) => {
                if (input.type === "checkbox") input.checked = false;
                else input.value = "";
            });
        } else if (deleteInput) {
            deleteInput.checked = true;
            row.hidden = true;
        }
        recalculate();
    };

    rows.addEventListener("input", (event) => {
        if (event.target.matches('input[name$="-product"]')) {
            const price = priceByProduct.get(event.target.value.trim().toLowerCase());
            const priceInput = event.target.closest("[data-invoice-item]")
                .querySelector('input[name$="-unit_price"]');
            if (price !== undefined && (!priceInput.value || priceInput.dataset.autoPrice === "true")) {
                priceInput.value = price.toFixed(2);
                priceInput.dataset.autoPrice = "true";
            }
        } else if (event.target.matches('input[name$="-unit_price"]')) {
            event.target.dataset.autoPrice = "false";
        }
        if (event.target.matches('input[name$="-quantity"], input[name$="-unit_price"]')) {
            recalculate();
        }
    });
    rows.addEventListener("click", (event) => {
        const removeButton = event.target.closest("[data-invoice-remove]");
        if (removeButton) removeRow(removeButton.closest("[data-invoice-item]"));
    });
    addButton.addEventListener("click", () => {
        const row = appendRow();
        row.querySelector('input[name$="-product"]')?.focus();
    });
    form.querySelector('[name="discount"]').addEventListener("input", recalculate);

    const customerSelect = form.querySelector('[name="customer"]');
    customerSelect.addEventListener("change", () => {
        const option = customerSelect.selectedOptions[0];
        if (!option.value) return;
        const [name, phone, email] = option.textContent.split(" - ");
        const customerName = form.querySelector('[name="customer_name"]');
        const customerPhone = form.querySelector('[name="customer_phone"]');
        const customerEmail = form.querySelector('[name="customer_email"]');
        if (customerName) customerName.value = name.trim();
        if (customerPhone && phone?.trim() !== "No phone") customerPhone.value = phone?.trim() || "";
        if (customerEmail && email?.trim() !== "No email") customerEmail.value = email?.trim() || "";
    });

    recalculate();
})();
