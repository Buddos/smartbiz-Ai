(() => {
    const form = document.querySelector("#hardwareSaleForm");
    if (!form) return;

    const grid = document.querySelector("#hardwareProductGrid");
    const search = document.querySelector("#hardwareProductSearch");
    const noResults = document.querySelector("#hardwareNoProducts");
    const cart = document.querySelector("#hardwareCartLines");
    const totalForms = document.querySelector("#id_sale_items-TOTAL_FORMS");
    const rowTemplate = document.querySelector("#hardwareCartLineTemplate");
    const currency = document.querySelector(".hardware-pos-page")?.dataset.currency || "";
    const money = (amount) => `${currency} ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    let activeCategory = "all";

    const rows = () => Array.from(cart.querySelectorAll("[data-hardware-cart-line]")).filter((row) => !row.hidden);
    const field = (row, suffix) => row.querySelector(`[name$="-${suffix}"]`);

    const updateTotals = () => {
        let subtotal = 0;
        let units = 0;
        let count = 0;
        rows().forEach((row) => {
            const quantity = Math.max(0, Number.parseFloat(field(row, "quantity")?.value) || 0);
            const price = Math.max(0, Number.parseFloat(field(row, "unit_price")?.value) || 0);
            const lineTotal = quantity * price;
            subtotal += lineTotal;
            units += quantity;
            if (field(row, "product")?.value.trim()) count += 1;
            const lineTotalElement = row.querySelector("[data-hardware-line-total]");
            if (lineTotalElement) lineTotalElement.textContent = money(lineTotal);
        });
        const discountInput = form.querySelector('[name="discount"]');
        const discount = Math.min(subtotal, Math.max(0, Number.parseFloat(discountInput?.value) || 0));
        const due = Math.max(0, subtotal - discount);
        document.querySelector("#hardwareCartCount").textContent = String(count);
        document.querySelector("#hardwareSubtotal").textContent = money(subtotal);
        document.querySelector("#hardwareDiscount").textContent = `− ${money(discount)}`;
        document.querySelector("#hardwareTotal").textContent = money(due);
        document.querySelector("#hardwareSubmitTotal").textContent = money(due);
        document.querySelector("#hardwareCartSummary").textContent = `${count} product${count === 1 ? "" : "s"} · ${units} unit${units === 1 ? "" : "s"}`;
    };

    const addRow = () => {
        const index = Number.parseInt(totalForms.value, 10);
        const html = rowTemplate.innerHTML.replaceAll("__prefix__", String(index));
        cart.insertAdjacentHTML("beforeend", html);
        totalForms.value = String(index + 1);
        return cart.lastElementChild;
    };

    const addProduct = (productButton) => {
        const productName = productButton.dataset.productName;
        const stock = Number.parseFloat(productButton.dataset.productStock) || 0;
        let row = rows().find((candidate) => {
            const productInput = field(candidate, "product");
            return productInput && [productName, productButton.dataset.productSku].includes(productInput.value.trim());
        });
        if (row) {
            const quantityInput = field(row, "quantity");
            const quantity = Number.parseFloat(quantityInput.value) || 0;
            if (quantity >= stock) {
                quantityInput.setCustomValidity(`Only ${stock} unit(s) are available.`);
                quantityInput.reportValidity();
                quantityInput.setCustomValidity("");
                return;
            }
            quantityInput.value = String(quantity + 1);
        } else {
            row = rows().find((candidate) => !field(candidate, "product")?.value.trim()) || addRow();
            field(row, "product").value = productName;
            field(row, "quantity").value = "1";
            field(row, "unit_price").value = productButton.dataset.productPrice || "0";
        }
        updateTotals();
    };

    const filterProducts = () => {
        const phrase = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        grid.querySelectorAll("[data-hardware-add-product]").forEach((product) => {
            const matchesText = [product.dataset.productName, product.dataset.productSku, product.dataset.productBarcode]
                .some((value) => (value || "").toLocaleLowerCase().includes(phrase));
            const matchesCategory = activeCategory === "all" || product.dataset.productCategory === activeCategory;
            product.hidden = !matchesText || !matchesCategory;
            if (!product.hidden) visible += 1;
        });
        noResults.hidden = visible > 0;
    };

    grid.addEventListener("click", (event) => {
        const product = event.target.closest("[data-hardware-add-product]");
        if (product && !product.disabled) addProduct(product);
    });
    search.addEventListener("input", filterProducts);
    document.querySelectorAll("[data-hardware-category]").forEach((button) => {
        button.addEventListener("click", () => {
            activeCategory = button.dataset.hardwareCategory;
            document.querySelectorAll("[data-hardware-category]").forEach((item) => item.classList.toggle("is-active", item === button));
            filterProducts();
        });
    });
    cart.addEventListener("input", updateTotals);
    cart.addEventListener("click", (event) => {
        const remove = event.target.closest("[data-hardware-remove]");
        if (!remove) return;
        const row = remove.closest("[data-hardware-cart-line]");
        const deleted = field(row, "DELETE");
        if (deleted) deleted.checked = true;
        row.hidden = true;
        updateTotals();
    });
    document.querySelector("#hardwareAddManual").addEventListener("click", () => {
        const row = addRow();
        field(row, "product")?.focus();
        updateTotals();
    });
    document.querySelector("#hardwareClearCart").addEventListener("click", () => {
        rows().forEach((row) => {
            const deleted = field(row, "DELETE");
            if (deleted) deleted.checked = true;
            row.hidden = true;
        });
        updateTotals();
    });
    form.querySelector('[name="discount"]')?.addEventListener("input", updateTotals);

    const paymentSelect = form.querySelector('select[name="payment_method"]');
    document.querySelectorAll("[data-hardware-payment]").forEach((button) => {
        button.addEventListener("click", () => {
            if (!paymentSelect) return;
            paymentSelect.value = button.dataset.hardwarePayment;
            paymentSelect.dispatchEvent(new Event("change", { bubbles: true }));
            document.querySelectorAll("[data-hardware-payment]").forEach((choice) => {
                choice.setAttribute("aria-pressed", String(choice === button));
            });
        });
    });
    const customerSelect = form.querySelector("[data-hardware-customer]");
    customerSelect?.addEventListener("change", () => {
        const option = customerSelect.selectedOptions[0];
        if (!option?.value) return;
        document.querySelector("#hardwareCustomerName").value = option.dataset.name || "";
        document.querySelector("#hardwareCustomerPhone").value = option.dataset.phone || "";
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
            event.preventDefault();
            search.focus();
        } else if (event.key === "F9") {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    updateTotals();
})();
