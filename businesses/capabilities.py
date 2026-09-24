"""Capability registry and business-category presets for generated navigation."""

from copy import deepcopy

CAPABILITY_REGISTRY = {
    "inventory": {
        "label": "Inventory & stock",
        "description": "Products, stock levels, and suppliers",
        "pages": [
            {"label": "Products", "icon": "fa-box", "url": "products:list"},
            {"label": "Inventory", "icon": "fa-warehouse", "url": "inventory:dashboard"},
        ],
    },
    "customer_credit": {
        "label": "Customer credit",
        "description": "Track customer balances and due dates",
        "pages": [{"label": "Customers", "icon": "fa-users", "url": "customers:list"}],
    },
    "menu": {
        "label": "Menu & recipes",
        "description": "Menu items, ingredients, and food cost",
        "pages": [],
    },
    "tables": {
        "label": "Table & order management",
        "description": "Tables, orders, and service duration",
        "pages": [{"label": "Table orders", "icon": "fa-chair", "url": "sales:list"}],
    },
    "appointments": {
        "label": "Appointments & bookings",
        "description": "Calendar, bookings, and services",
        "pages": [],
    },
    "staff": {
        "label": "Staff & shift scheduling",
        "description": "Staff schedules and shifts",
        "pages": [],
    },
    "clients": {
        "label": "Client / patient records",
        "description": "Client history and preferences",
        "pages": [{"label": "Clients", "icon": "fa-users", "url": "customers:list"}],
    },
    "jobs": {
        "label": "Jobs & quotes",
        "description": "Jobs, quotes, and invoices",
        "pages": [{"label": "Invoices", "icon": "fa-file-invoice", "url": "sales:list"}],
    },
    "delivery": {
        "label": "Delivery & logistics",
        "description": "Deliveries, routes, and ETAs",
        "pages": [],
    },
    "equipment": {
        "label": "Equipment & assets",
        "description": "Equipment and maintenance",
        "pages": [],
    },
}

CATEGORY_PRESETS = {
    "RETAIL": ["inventory"],
    "RESTAURANT": ["menu", "tables", "inventory"],
    "SALON": ["appointments", "staff", "clients"],
    "WHOLESALE": ["inventory", "delivery", "customer_credit"],
    "SERVICE": ["jobs", "clients", "staff"],
    "ELECTRONICS": ["inventory", "customer_credit"],
    "BOUTIQUE": ["inventory", "customer_credit"],
    "HARDWARE": ["inventory", "customer_credit"],
    "FREELANCE": ["jobs", "clients"],
    "OTHER": [],
}

CORE_NAVIGATION = [
    {"label": "Sales", "icon": "fa-receipt", "url": "sales:list"},
    {"label": "Expenses", "icon": "fa-wallet", "url": "expenses:list"},
    {"label": "AI Insights", "icon": "fa-brain", "url": "ai_engine:home"},
    {"label": "Assistant", "icon": "fa-robot", "url": "ai_engine:home"},
]

CORE_SALE_TEMPLATE = {
    "id": "standard",
    "label": "Standard sale",
    "title": "New Business Sale",
    "description": "Record a sale using the tools selected for this business.",
    "entry_template": "sales/entries/other.html",
    "item_label": "Sale items",
    "product_label": "Product",
    "sections": ["customer", "items", "payment"],
    "fields": ["customer", "customer_name", "customer_phone", "customer_email", "payment_method", "notes"],
}

BUSINESS_SALE_PROFILES = {
    "RESTAURANT": {
        "label": "Restaurant order",
        "title": "New Restaurant Order",
        "description": "Capture menu items, table service, and payment for this order.",
        "item_label": "Menu items",
        "product_label": "Menu item",
        "entry_template": "sales/entries/restaurant.html",
    },
    "RETAIL": {
        "label": "Retail sale",
        "title": "New Retail Sale",
        "description": "Record products sold from your retail catalog.",
        "entry_template": "sales/entries/retail.html",
    },
    "ELECTRONICS": {
        "label": "Electronics sale",
        "title": "New Electronics Sale",
        "description": "Record the device, customer, and payment details for this sale.",
        "entry_template": "sales/entries/electronics.html",
    },
    "SALON": {
        "label": "Service appointment sale",
        "title": "New Service Sale",
        "description": "Record services delivered and the client payment.",
        "item_label": "Services",
        "product_label": "Service",
        "entry_template": "sales/entries/salon.html",
    },
    "SERVICE": {
        "label": "Service invoice",
        "title": "New Service Invoice",
        "description": "Record the work completed and invoice the client.",
        "entry_template": "sales/entries/service.html",
    },
    "WHOLESALE": {
        "label": "Wholesale sale",
        "title": "New Wholesale Sale",
        "description": "Capture the buyer, bulk products, and delivery or payment terms.",
        "item_label": "Bulk order items",
        "product_label": "Product or SKU",
        "entry_template": "sales/entries/wholesale.html",
    },
    "BOUTIQUE": {
        "label": "Boutique sale",
        "title": "New Boutique Sale",
        "description": "Record a collection item sale and connect it to the customer.",
        "item_label": "Collection items",
        "product_label": "Collection item",
        "entry_template": "sales/entries/boutique.html",
    },
    "HARDWARE": {
        "label": "Hardware sale",
        "title": "New Hardware Sale",
        "description": "Record materials sold and the customer or contractor buying them.",
        "item_label": "Hardware items",
        "product_label": "Material or SKU",
        "entry_template": "sales/entries/hardware.html",
    },
    "FREELANCE": {
        "label": "Client invoice",
        "title": "New Client Invoice",
        "description": "Bill a client for completed work or a project milestone.",
        "item_label": "Billable work",
        "product_label": "Service or project",
        "entry_template": "sales/entries/freelance.html",
    },
    "OTHER": {
        "label": "Business sale",
        "title": "New Business Sale",
        "description": "Record a sale using the tools selected for this business.",
        "entry_template": "sales/entries/other.html",
    },
}

DASHBOARD_PROFILES = {
    "RETAIL": {
        "id": "retail",
        "title": "Retail command center",
        "focus": "Stock movement, fast checkout, and your best-selling products.",
        "metric_label": "Products needing attention",
        "primary_action": "New retail sale",
    },
    "RESTAURANT": {
        "id": "restaurant",
        "title": "Restaurant service desk",
        "focus": "Table orders, menu sales, and service flow for today.",
        "metric_label": "Open table orders",
        "primary_action": "Start restaurant order",
    },
    "SALON": {
        "id": "salon",
        "title": "Salon bookings desk",
        "focus": "Appointments, client history, and services delivered.",
        "metric_label": "Service sales this period",
        "primary_action": "Record service sale",
    },
    "WHOLESALE": {
        "id": "wholesale",
        "title": "Wholesale operations",
        "focus": "Large orders, customer credit, and delivery movement.",
        "metric_label": "Orders in progress",
        "primary_action": "Create wholesale sale",
    },
    "SERVICE": {
        "id": "service",
        "title": "Service delivery desk",
        "focus": "Jobs, client records, quotes, and invoices in one place.",
        "metric_label": "Service invoices",
        "primary_action": "Create service invoice",
    },
    "ELECTRONICS": {
        "id": "electronics",
        "title": "Electronics sales desk",
        "focus": "Device stock, customer purchases, and payment follow-up.",
        "metric_label": "Units in catalog",
        "primary_action": "Record electronics sale",
    },
    "BOUTIQUE": {
        "id": "boutique",
        "title": "Boutique collection desk",
        "focus": "Collection stock, customer purchases, and sales performance.",
        "metric_label": "Collection items",
        "primary_action": "Record boutique sale",
    },
    "HARDWARE": {
        "id": "hardware",
        "title": "Hardware stock desk",
        "focus": "Fast-moving materials, stock levels, and customer balances.",
        "metric_label": "Stock alerts",
        "primary_action": "Record hardware sale",
    },
    "FREELANCE": {
        "id": "freelance",
        "title": "Freelance client desk",
        "focus": "Client work, invoices, and your service pipeline.",
        "metric_label": "Client invoices",
        "primary_action": "Create client invoice",
    },
    "OTHER": {
        "id": "other",
        "title": "Business command center",
        "focus": "Your selected tools, sales, customers, and business health.",
        "metric_label": "Total sales",
        "primary_action": "Record sale",
    },
}

SALE_TEMPLATE_BY_CAPABILITY = {
    "inventory": {
        "id": "inventory",
        "label": "Inventory sale",
        "item_label": "Products",
        "product_label": "Product or SKU",
    },
    "menu": {
        "id": "menu",
        "label": "Menu sale",
        "item_label": "Menu items",
        "product_label": "Menu item",
    },
    "tables": {
        "sections": ["customer", "items", "table", "payment"],
        "table_label": "Table or order reference",
    },
    "appointments": {
        "sections": ["customer", "items", "booking", "payment"],
        "item_label": "Services",
        "product_label": "Service",
        "booking_label": "Booking details",
    },
    "jobs": {
        "id": "invoice",
        "label": "Job invoice",
        "item_label": "Quoted work",
        "product_label": "Job or service",
    },
    "delivery": {
        "sections": ["customer", "items", "delivery", "payment"],
        "delivery_label": "Delivery details",
    },
    "customer_credit": {
        "sections": ["customer", "items", "credit", "payment"],
        "credit_label": "Credit terms",
    },
}


def capabilities_for_business(business):
    """Return saved capabilities, initializing legacy businesses from their type."""
    enabled = list(business.enabled_capabilities or [])
    if not enabled:
        enabled = list(CATEGORY_PRESETS.get(business.business_type, []))
    return [capability_id for capability_id in enabled if capability_id in CAPABILITY_REGISTRY]


def navigation_for_business(business):
    """Build the ordered navigation list from core pages and enabled capabilities."""
    navigation = []
    seen = set()
    for item in CORE_NAVIGATION:
        if item["url"] not in seen:
            navigation.append(item)
            seen.add(item["url"])
    for capability_id in capabilities_for_business(business):
        for item in CAPABILITY_REGISTRY[capability_id]["pages"]:
            if item["url"] not in seen:
                navigation.append(item)
                seen.add(item["url"])
    return navigation


def dashboard_capabilities_for_business(business):
    """Return selected capabilities with dashboard-ready labels and links."""
    cards = []
    for capability_id in capabilities_for_business(business):
        capability = CAPABILITY_REGISTRY[capability_id]
        pages = capability["pages"]
        cards.append({
            "id": capability_id,
            "label": capability["label"],
            "description": capability["description"],
            "icon": pages[0]["icon"] if pages else "fa-puzzle-piece",
            "url": pages[0]["url"] if pages else "sales:create",
        })
    return cards


def dashboard_profile_for_business(business):
    """Resolve the dashboard workspace selected by the registered business type."""
    profile = deepcopy(DASHBOARD_PROFILES.get(business.business_type, DASHBOARD_PROFILES["OTHER"]))
    profile["business_type"] = business.business_type
    profile["capabilities"] = capabilities_for_business(business)
    return profile


def sale_template_for_business(business):
    """Resolve the sale form presentation from the business capabilities.

    The returned dictionary is presentation metadata only. Sale persistence remains
    shared, so changing capabilities cannot change the sale model contract.
    """
    template = deepcopy(CORE_SALE_TEMPLATE)
    capabilities = capabilities_for_business(business)

    template.update(BUSINESS_SALE_PROFILES.get(business.business_type, {}))

    for capability_id in capabilities:
        overrides = SALE_TEMPLATE_BY_CAPABILITY.get(capability_id, {})
        for key, value in overrides.items():
            if key == "sections":
                for section in value:
                    if section not in template["sections"]:
                        template["sections"].insert(-1, section)
            elif key == "id" and template["id"] == "standard":
                template[key] = value
            else:
                template[key] = value

    template["capabilities"] = capabilities
    template["business_type"] = business.business_type
    return template


def resolve_business_configuration(business):
    """Resolve all capability-driven business presentation outputs in one pass."""
    return {
        "navigation": navigation_for_business(business),
        "dashboard_capabilities": dashboard_capabilities_for_business(business),
        "sale_template": sale_template_for_business(business),
    }
