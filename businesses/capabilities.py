"""Capability registry and business-category presets for generated navigation."""

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
        "pages": [],
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
