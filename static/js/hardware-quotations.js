(() => {
    const form = document.querySelector("#hardwareQuotationForm");
    if (!form) return;

    const container = document.querySelector("#hardwareQuoteLines");
    const template = document.querySelector("#hardwareQuoteEmptyLine");
    const totalForms = document.querySelector("#id_items-TOTAL_FORMS");
    const addButton = document.querySelector("#hardwareAddQuoteLine");
    const products = JSON.parse(document.querySelector("#hardwareQuotationProductPrices").textContent);
    const priceById = new Map(products.map((product) => [String(product.id), product.selling_price]));

    const removeLine = (line) => {
        const deleteInput = line.querySelector('input[name$="-DELETE"]');
        const visibleLines = Array.from(container.querySelectorAll("[data-quote-line]"))
            .filter((candidate) => !candidate.hidden);
        if (visibleLines.length === 1) {
            line.querySelectorAll("select, input").forEach((input) => {
                if (input.type === "checkbox") input.checked = false;
                else input.value = "";
            });
            return;
        }
        if (deleteInput) {
            deleteInput.checked = true;
            line.hidden = true;
        }
    };

    const addLine = () => {
        const index = Number.parseInt(totalForms.value, 10);
        const html = template.innerHTML.replaceAll("__prefix__", String(index));
        container.insertAdjacentHTML("beforeend", html);
        totalForms.value = String(index + 1);
        return container.lastElementChild;
    };

    container.addEventListener("change", (event) => {
        const productSelect = event.target.closest('select[name$="-product"]');
        if (!productSelect) return;
        const priceInput = productSelect.closest("[data-quote-line]").querySelector('input[name$="-unit_price"]');
        const selectedPrice = priceById.get(productSelect.value);
        if (priceInput && selectedPrice !== undefined && (!priceInput.value || priceInput.dataset.autoPrice === "true")) {
            priceInput.value = selectedPrice;
            priceInput.dataset.autoPrice = "true";
        }
    });
    container.addEventListener("input", (event) => {
        if (event.target.matches('input[name$="-unit_price"]')) {
            event.target.dataset.autoPrice = "false";
        }
    });
    container.addEventListener("click", (event) => {
        const remove = event.target.closest("[data-remove-quote-line]");
        if (remove) removeLine(remove.closest("[data-quote-line]"));
    });
    addButton.addEventListener("click", () => {
        const line = addLine();
        line.querySelector('select[name$="-product"]')?.focus();
    });

    const customerSelect = form.querySelector('select[name="customer"]');
    customerSelect?.addEventListener("change", () => {
        const option = customerSelect.selectedOptions[0];
        if (!option?.value) return;
        const [customerName, phone, email] = option.textContent.split(" - ");
        const nameInput = form.querySelector('input[name="customer_name"]');
        const phoneInput = form.querySelector('input[name="customer_phone"]');
        const emailInput = form.querySelector('input[name="customer_email"]');
        if (nameInput) nameInput.value = customerName.trim();
        if (phoneInput && phone?.trim() !== "No phone") phoneInput.value = phone?.trim() || "";
        if (emailInput && email?.trim() !== "No email") emailInput.value = email?.trim() || "";
    });
})();
