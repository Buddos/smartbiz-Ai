document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("electronicsSaleForm");
    if (!form) return;

    const root = document.querySelector(".e-sale-create");
    const cartRows = document.getElementById("cartRows");
    const rowTemplate = document.getElementById("cartRowTemplate");
    const totalForms = document.getElementById("id_sale_items-TOTAL_FORMS");
    const productSearch = document.getElementById("productSearch");
    const customerSearch = document.getElementById("customerSearch");
    const customerSelect = document.querySelector("[data-customer-select]");
    const paymentSelect = document.getElementById("id_payment_method");
    const discountInput = document.getElementById("id_discount");
    const completeButton = document.getElementById("completeSale");
    const productButtons = Array.from(document.querySelectorAll(".e-sale-product"));
    const currency = root.dataset.currency || "KES";
    const taxEnabled = root.dataset.taxEnabled === "true";
    const taxRate = Number.parseFloat(root.dataset.taxRate || "0") || 0;
    const taxInclusive = root.dataset.taxInclusive === "true";
    let activeCategory = "all";
    let dirty = false;

    const money = (value) => `${currency} ${Number(value || 0).toLocaleString("en", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
    const activeRows = () => Array.from(cartRows.querySelectorAll("[data-cart-row]")).filter((row) => {
        const deleted = row.querySelector('input[name$="-DELETE"]');
        return !deleted?.checked && row.style.display !== "none";
    });
    const rowFields = (row) => ({
        product: row.querySelector('input[name$="-product"]'),
        quantity: row.querySelector('input[name$="-quantity"]'),
        price: row.querySelector('input[name$="-unit_price"]'),
        deleted: row.querySelector('input[name$="-DELETE"]'),
    });

    function calculateTotals() {
        let subtotal = 0;
        let taxableSubtotal = 0;
        let units = 0;
        let lines = 0;
        activeRows().forEach((row) => {
            const fields = rowFields(row);
            const name = fields.product?.value.trim();
            const quantity = Math.max(0, Number.parseInt(fields.quantity?.value || "0", 10) || 0);
            const price = Math.max(0, Number.parseFloat(fields.price?.value || "0") || 0);
            const lineTotal = name && quantity > 0 ? quantity * price : 0;
            subtotal += lineTotal;
            if (name && quantity > 0 && row.dataset.productTaxable === "true") taxableSubtotal += lineTotal;
            if (name && quantity > 0) {
                lines += 1;
                units += quantity;
            }
            const lineTotalTarget = row.querySelector("[data-line-total]");
            if (lineTotalTarget) lineTotalTarget.textContent = money(lineTotal);
        });

        const requestedDiscount = Math.max(0, Number.parseFloat(discountInput?.value || "0") || 0);
        const discount = Math.min(requestedDiscount, subtotal);
        discountInput.max = subtotal.toFixed(2);
        const tax = taxEnabled
            ? (taxInclusive ? taxableSubtotal * taxRate / (100 + taxRate) : taxableSubtotal * taxRate / 100)
            : 0;
        const total = Math.max(0, subtotal + (taxInclusive ? 0 : tax) - discount);
        const itemSummary = `${lines} product${lines === 1 ? "" : "s"} · ${units} unit${units === 1 ? "" : "s"}`;
        document.getElementById("saleSubtotal").textContent = money(subtotal);
        const taxTarget = document.getElementById("saleTax");
        if (taxTarget) taxTarget.textContent = money(tax);
        document.getElementById("saleDiscount").textContent = `− ${money(discount)}`;
        document.getElementById("saleTotal").textContent = money(total);
        document.getElementById("paymentTotal").textContent = money(total);
        document.getElementById("completeTotal").textContent = money(total);
        document.getElementById("saleItemSummary").textContent = itemSummary;
        document.getElementById("paymentItemCount").textContent = `${lines} item${lines === 1 ? "" : "s"} · ${units} unit${units === 1 ? "" : "s"}`;
        document.getElementById("cartCount").textContent = String(lines);
        updatePaymentNote();
        completeButton.disabled = lines === 0;
    }

    function addEmptyRow() {
        const index = Number.parseInt(totalForms.value, 10);
        const html = rowTemplate.innerHTML.replaceAll("__prefix__", String(index));
        cartRows.insertAdjacentHTML("beforeend", html);
        totalForms.value = String(index + 1);
        return cartRows.lastElementChild;
    }

    function addProduct(button) {
        const name = button.dataset.productName || "";
        const sku = button.dataset.productSku || "";
        const price = button.dataset.productPrice || "";
        const stock = Number.parseInt(button.dataset.productStock || "0", 10);
        if (!name || stock <= 0) return;

        let row = activeRows().find((candidate) => {
            const value = rowFields(candidate).product?.value.trim().toLocaleLowerCase();
            return value && [name, sku].some((match) => match.toLocaleLowerCase() === value);
        });
        if (row) {
            const fields = rowFields(row);
            const nextQuantity = (Number.parseInt(fields.quantity.value || "0", 10) || 0) + 1;
            if (nextQuantity > stock) {
                fields.quantity.value = String(stock);
                fields.quantity.dispatchEvent(new Event("input", { bubbles: true }));
                return;
            }
            fields.quantity.value = String(nextQuantity);
        } else {
            row = activeRows().find((candidate) => !rowFields(candidate).product?.value.trim()) || addEmptyRow();
            const fields = rowFields(row);
            if (fields.deleted) fields.deleted.checked = false;
            fields.product.value = name;
            fields.quantity.value = "1";
            fields.quantity.max = String(stock);
            fields.price.value = price;
            row.dataset.productTaxable = button.dataset.productTaxable || "false";
        }
        row.dataset.stockLimit = String(stock);
        rowFields(row).quantity.dispatchEvent(new Event("input", { bubbles: true }));
        dirty = true;
        calculateTotals();
    }

    function updatePaymentNote() {
        const note = document.getElementById("paymentNote");
        if (paymentSelect.value === "CREDIT") {
            note.textContent = customerSelect.value
                ? "This sale will be recorded as credit; its unpaid balance remains due."
                : "Select a saved customer before completing a credit sale.";
            note.className = "e-sale-payment-note is-credit";
            document.getElementById("customerHelp").textContent = "A saved customer is required for credit sales.";
        } else if (["CASH", "M-PESA", "CARD", "BANK"].includes(paymentSelect.value)) {
            note.textContent = "The current sale flow records the full total as paid when you save.";
            note.className = "e-sale-payment-note is-paid";
            document.getElementById("customerHelp").textContent = "Leave customer blank for a walk-in sale.";
        } else {
            note.textContent = "Payment status will follow this method in the sales record.";
            note.className = "e-sale-payment-note";
            document.getElementById("customerHelp").textContent = "Leave customer blank for a walk-in sale.";
        }
        document.querySelectorAll("[data-payment-choice]").forEach((button) => {
            button.setAttribute("aria-pressed", String(button.dataset.paymentChoice === paymentSelect.value));
        });
        document.getElementById("transactionCodeGroup").hidden = !["M-PESA", "CARD", "BANK"].includes(paymentSelect.value);
        completeButton.disabled = activeRows().every((row) => !rowFields(row).product?.value.trim())
            || (paymentSelect.value === "CREDIT" && !customerSelect.value);
    }

    function filterProducts() {
        const query = productSearch.value.trim().toLocaleLowerCase();
        let visibleCount = 0;
        productButtons.forEach((button) => {
            const searchable = [
                button.dataset.productName,
                button.dataset.productSku,
                button.dataset.productBarcode,
            ].join(" ").toLocaleLowerCase();
            const categoryMatches = activeCategory === "all" || button.dataset.productCategory === activeCategory;
            const visible = categoryMatches && (!query || searchable.includes(query));
            button.hidden = !visible;
            if (visible) visibleCount += 1;
        });
        document.getElementById("noProductResults").hidden = visibleCount !== 0;
    }

    productButtons.forEach((button) => button.addEventListener("click", () => addProduct(button)));
    document.querySelectorAll("[data-add-product]:not(.e-sale-product)").forEach((button) => {
        button.addEventListener("click", () => addProduct(button));
    });
    document.querySelectorAll("[data-category-filter]").forEach((button) => {
        button.addEventListener("click", () => {
            activeCategory = button.dataset.categoryFilter;
            document.querySelectorAll("[data-category-filter]").forEach((categoryButton) => {
                categoryButton.classList.toggle("is-active", categoryButton === button);
            });
            filterProducts();
        });
    });
    productSearch.addEventListener("input", filterProducts);

    document.getElementById("addCartRow").addEventListener("click", () => {
        addEmptyRow()?.querySelector('input[name$="-product"]')?.focus();
        dirty = true;
    });
    document.getElementById("clearCart").addEventListener("click", () => {
        activeRows().forEach((row) => {
            const deleted = rowFields(row).deleted;
            if (deleted) {
                deleted.checked = true;
                row.style.display = "none";
            } else {
                row.remove();
            }
        });
        addEmptyRow();
        dirty = true;
        calculateTotals();
    });

    cartRows.addEventListener("click", (event) => {
        const removeButton = event.target.closest("[data-remove-row]");
        if (removeButton) {
            const row = removeButton.closest("[data-cart-row]");
            const deleted = rowFields(row).deleted;
            if (deleted) {
                deleted.checked = true;
                row.style.display = "none";
            } else {
                row.remove();
            }
            dirty = true;
            calculateTotals();
            return;
        }
        const stepButton = event.target.closest("[data-quantity-step]");
        if (stepButton) {
            const fields = rowFields(stepButton.closest("[data-cart-row]"));
            const current = Number.parseInt(fields.quantity.value || "0", 10) || 0;
            const next = Math.max(1, current + Number.parseInt(stepButton.dataset.quantityStep, 10));
            const maximum = Number.parseInt(fields.quantity.max || "0", 10);
            fields.quantity.value = maximum ? String(Math.min(next, maximum)) : String(next);
            dirty = true;
            calculateTotals();
        }
    });
    cartRows.addEventListener("input", (event) => {
        if (event.target.matches('input[name$="-product"]')) {
            const typed = event.target.value.trim().toLocaleLowerCase();
            const matchingProduct = productButtons.find((button) => (
                [button.dataset.productName, button.dataset.productSku, button.dataset.productBarcode]
                    .some((value) => value && value.toLocaleLowerCase() === typed)
            ));
            if (matchingProduct) {
                const row = event.target.closest("[data-cart-row]");
                const fields = rowFields(row);
                fields.quantity.max = matchingProduct.dataset.productStock;
                row.dataset.stockLimit = matchingProduct.dataset.productStock;
                row.dataset.productTaxable = matchingProduct.dataset.productTaxable || "false";
                if (!fields.price.value) fields.price.value = matchingProduct.dataset.productPrice;
            }
        }
        if (event.target.matches('input[name$="-quantity"], input[name$="-unit_price"], input[name$="-product"], #id_discount')) {
            dirty = true;
            calculateTotals();
        }
    });
    cartRows.addEventListener("change", (event) => {
        if (event.target.matches('input[name$="-quantity"]')) {
            const stockLimit = Number.parseInt(event.target.closest("[data-cart-row]").dataset.stockLimit || "0", 10);
            if (stockLimit && Number.parseInt(event.target.value || "0", 10) > stockLimit) {
                event.target.value = String(stockLimit);
            }
            calculateTotals();
        }
    });

    document.querySelectorAll("[data-payment-choice]").forEach((button) => {
        button.addEventListener("click", () => {
            paymentSelect.value = button.dataset.paymentChoice;
            paymentSelect.dispatchEvent(new Event("change", { bubbles: true }));
        });
    });
    paymentSelect.addEventListener("change", () => {
        dirty = true;
        updatePaymentNote();
    });
    customerSelect.addEventListener("change", () => {
        const option = customerSelect.options[customerSelect.selectedIndex];
        if (customerSelect.value && option) {
            document.getElementById("customer_name").value = option.dataset.name || "";
            document.getElementById("customer_phone").value = option.dataset.phone || "";
            document.getElementById("customer_email").value = option.dataset.email || "";
        }
        dirty = true;
        updatePaymentNote();
    });
    customerSearch.addEventListener("input", () => {
        const query = customerSearch.value.trim().toLocaleLowerCase();
        Array.from(customerSelect.options).forEach((option, index) => {
            if (index === 0) {
                option.hidden = false;
                return;
            }
            option.hidden = !`${option.dataset.name || ""} ${option.dataset.phone || ""}`
                .toLocaleLowerCase().includes(query);
        });
    });
    discountInput.addEventListener("input", () => {
        dirty = true;
        calculateTotals();
    });

    form.addEventListener("submit", (event) => {
        const creditWithoutCustomer = paymentSelect.value === "CREDIT" && !customerSelect.value;
        if (activeRows().every((row) => !rowFields(row).product?.value.trim()) || creditWithoutCustomer) {
            event.preventDefault();
            if (creditWithoutCustomer) customerSelect.focus();
        }
    });
    document.querySelectorAll("#cancelSale, .e-sale-back").forEach((link) => {
        link.addEventListener("click", (event) => {
            if (dirty && !window.confirm("Leave this page? The sale in progress will not be saved.")) {
                event.preventDefault();
            }
        });
    });
    document.addEventListener("keydown", (event) => {
        const target = event.target;
        const editing = target instanceof HTMLElement
            && (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName));
        if (event.key === "/" && !editing) {
            event.preventDefault();
            productSearch.focus();
        } else if (event.key === "F5") {
            event.preventDefault();
            discountInput.focus();
        } else if (event.key === "F8") {
            event.preventDefault();
            customerSearch.focus();
        } else if (event.key === "F9" && !event.repeat) {
            event.preventDefault();
            if (!completeButton.disabled) form.requestSubmit();
        } else if (!editing && ["1", "2", "3", "4"].includes(event.key)) {
            const commonMethods = ["CASH", "M-PESA", "CARD", "CREDIT"];
            const method = commonMethods[Number.parseInt(event.key, 10) - 1];
            if (paymentSelect.querySelector(`option[value="${method}"]`)) {
                paymentSelect.value = method;
                paymentSelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
        } else if (["ArrowDown", "ArrowUp"].includes(event.key) && target === productSearch) {
            const matches = productButtons.filter((button) => !button.hidden && !button.disabled);
            if (matches.length) {
                event.preventDefault();
                matches[0].focus();
            }
        } else if (["ArrowDown", "ArrowUp"].includes(event.key) && target.matches?.(".e-sale-product")) {
            const matches = productButtons.filter((button) => !button.hidden && !button.disabled);
            const currentIndex = matches.indexOf(target);
            const step = event.key === "ArrowDown" ? 1 : -1;
            const next = matches[(currentIndex + step + matches.length) % matches.length];
            if (next) {
                event.preventDefault();
                next.focus();
            }
        } else if (event.key === "Enter" && target === productSearch) {
            const firstMatch = productButtons.find((button) => !button.hidden && !button.disabled);
            if (firstMatch) {
                event.preventDefault();
                addProduct(firstMatch);
            }
        } else if (event.key === "Escape" && dirty) {
            if (window.confirm("Leave this page? The sale in progress will not be saved.")) {
                window.location.assign(document.getElementById("cancelSale").href);
            }
        }
    });

    if (!paymentSelect.value) paymentSelect.value = "CASH";
    cartRows.querySelectorAll("[data-cart-row]").forEach((row) => {
        const productField = rowFields(row).product;
        const typed = productField?.value.trim().toLocaleLowerCase();
        const product = productButtons.find((button) => (
            [button.dataset.productName, button.dataset.productSku]
                .some((value) => value && value.toLocaleLowerCase() === typed)
        ));
        if (product) {
            row.dataset.stockLimit = product.dataset.productStock;
            row.dataset.productTaxable = product.dataset.productTaxable || "false";
            rowFields(row).quantity.max = product.dataset.productStock;
        }
    });
    calculateTotals();
});
