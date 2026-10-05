from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.decorators import business_required
from inventory.models import InventoryTransaction
from products.models import Product
from sales.models import Sale

from .forms import (
    RestaurantCashCloseForm,
    RestaurantCashMovementForm,
    RestaurantCashOpenForm,
    RestaurantPurchaseOrderForm,
    RestaurantReservationForm,
    RestaurantSupplierForm,
    RestaurantTableForm,
    restaurant_products,
)
from .models import (
    KitchenTicket,
    RestaurantCashShift,
    RestaurantRecipe,
    RestaurantRecipeIngredient,
    RestaurantPurchaseOrder,
    RestaurantPurchaseOrderLine,
    RestaurantSupplier,
    RestaurantReservation,
    RestaurantTable,
)


MANAGER_ROLES = {"OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"}
KITCHEN_STATIONS = ("GRILL", "FRY", "SALAD", "DESSERT", "BAR", "OTHER")


def _restaurant_business(request):
    business = request.user.business
    if not business or business.business_type != "RESTAURANT":
        raise Http404
    return business


def _manager_required(request):
    if request.user.role not in MANAGER_ROLES and not request.user.is_superuser:
        messages.error(request, "You do not have permission to manage restaurant settings.")
        return False
    return True


def _page(request, name, **context):
    return render(request, "restaurant/operations.html", {
        "page": name,
        "can_manage_restaurant": request.user.role in MANAGER_ROLES or request.user.is_superuser,
        **context,
    })


@login_required
@business_required
@never_cache
def tables_view(request):
    business = _restaurant_business(request)
    tables = list(
        RestaurantTable.objects.filter(business=business).prefetch_related("reservations")
    )
    counts = {status: 0 for status, _ in RestaurantTable.STATUS_CHOICES}
    for table in tables:
        counts[table.status] += 1
    form = RestaurantTableForm()
    if request.method == "POST":
        if not _manager_required(request):
            return redirect("restaurant:tables")
        form = RestaurantTableForm(request.POST)
        if form.is_valid():
            table = form.save(commit=False)
            table.business = business
            zone_count = sum(existing.zone == table.zone for existing in tables)
            table.position_x = zone_count % 8
            table.position_y = zone_count // 8
            try:
                table.save()
            except IntegrityError:
                form.add_error("number", "A table with this number already exists.")
            else:
                messages.success(request, f"Table {table.number} added.")
                return redirect("restaurant:tables")
    taken_cells = set()
    next_position_by_zone = {}
    for table in tables:
        cell = (table.zone, table.position_x, table.position_y)
        if cell in taken_cells:
            position = next_position_by_zone.get(table.zone, 0)
            while (table.zone, position % 8, position // 8) in taken_cells:
                position += 1
            table.position_x = position % 8
            table.position_y = position // 8
            next_position_by_zone[table.zone] = position + 1
            cell = (table.zone, table.position_x, table.position_y)
        taken_cells.add(cell)
    return _page(
        request,
        "tables",
        tables=tables,
        counts=counts,
        form=form,
        total_tables=sum(counts.values()),
        occupied=counts["OCCUPIED"] + counts["BILL_REQUESTED"],
    )


@login_required
@business_required
@require_POST
def table_layout_save(request):
    business = _restaurant_business(request)
    if not _manager_required(request):
        return redirect("restaurant:tables")
    table_ids = request.POST.getlist("table_id")
    x_positions = request.POST.getlist("position_x")
    y_positions = request.POST.getlist("position_y")
    tables = list(RestaurantTable.objects.filter(business=business))
    if not (len(table_ids) == len(x_positions) == len(y_positions) == len(tables)):
        messages.error(request, "The floor layout was not saved. Reload the page and try again.")
        return redirect("restaurant:tables")
    positions = {}
    tables_by_id = {str(table.pk): table for table in tables}
    occupied_positions = set()
    try:
        for table_id, raw_x, raw_y in zip(table_ids, x_positions, y_positions):
            table = tables_by_id.get(table_id)
            x = int(raw_x)
            y = int(raw_y)
            if table is None or not (0 <= x < 8 and 0 <= y <= 65535):
                raise ValueError
            cell = (table.zone, x, y)
            if cell in occupied_positions:
                messages.error(request, "Each table in a zone needs its own floor-plan position.")
                return redirect("restaurant:tables")
            occupied_positions.add(cell)
            positions[table.pk] = (x, y)
    except ValueError:
        messages.error(request, "Columns must be from 0 to 7 and rows must be nonnegative whole numbers.")
        return redirect("restaurant:tables")
    if {str(pk) for pk in positions} != {str(table.pk) for table in tables}:
        messages.error(request, "The floor layout was not saved. Reload the page and try again.")
        return redirect("restaurant:tables")
    with transaction.atomic():
        for table in tables:
            table.position_x, table.position_y = positions[table.pk]
        RestaurantTable.objects.bulk_update(tables, ["position_x", "position_y"])
    messages.success(request, "Floor layout saved.")
    return redirect("restaurant:tables")


@login_required
@business_required
@require_POST
def table_action(request, table_id, action):
    business = _restaurant_business(request)
    with transaction.atomic():
        table = get_object_or_404(
            RestaurantTable.objects.select_for_update(), business=business, pk=table_id
        )
        transitions = {
            "seat": {"AVAILABLE": "OCCUPIED", "RESERVED": "OCCUPIED"},
            "bill": {"OCCUPIED": "BILL_REQUESTED"},
            "clear": {"OCCUPIED": "AVAILABLE", "BILL_REQUESTED": "AVAILABLE", "NEEDS_ATTENTION": "AVAILABLE"},
            "attention": {"OCCUPIED": "NEEDS_ATTENTION"},
            "block": {"AVAILABLE": "BLOCKED"},
            "unblock": {"BLOCKED": "AVAILABLE"},
        }
        next_status = transitions.get(action, {}).get(table.status)
        if not next_status:
            messages.error(request, "That table action is not valid for its current status.")
        else:
            table.status = next_status
            if action == "clear" and RestaurantReservation.objects.filter(
                business=business,
                table=table,
                starts_at__gte=timezone.now(),
                status__in=["PENDING", "CONFIRMED"],
            ).exists():
                table.status = "RESERVED"
            table.seated_at = timezone.now() if next_status == "OCCUPIED" else None
            if table.status == "RESERVED":
                table.seated_at = None
            table.save(update_fields=["status", "seated_at", "updated_at"])
            if action == "seat":
                reservation = RestaurantReservation.objects.filter(
                    business=business,
                    table=table,
                    starts_at__range=(
                        timezone.now() - timedelta(minutes=30),
                        timezone.now() + timedelta(minutes=30),
                    ),
                    status__in=["PENDING", "CONFIRMED"],
                ).order_by("starts_at").first()
                if reservation:
                    reservation.status = "SEATED"
                    reservation.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Table {table.number} is now {table.get_status_display().lower()}.")
    return redirect("restaurant:tables")


@login_required
@business_required
@never_cache
def reservations_view(request):
    business = _restaurant_business(request)
    form = RestaurantReservationForm(business=business)
    if request.method == "POST":
        form = RestaurantReservationForm(request.POST, business=business)
        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.business = business
            reservation.created_by = request.user
            try:
                with transaction.atomic():
                    reservation.save()
                    if (
                        reservation.table
                        and reservation.status == "PENDING"
                        and reservation.table.status == "AVAILABLE"
                    ):
                        reservation.table.status = "RESERVED"
                        reservation.table.save(update_fields=["status", "updated_at"])
            except IntegrityError:
                form.add_error(None, "The reservation could not be saved. Please try again.")
            else:
                messages.success(request, f"Reservation {reservation.code} saved.")
                return redirect("restaurant:reservations")
    reservations = RestaurantReservation.objects.filter(
        business=business,
        starts_at__date__gte=timezone.localdate(),
        status__in=["PENDING", "CONFIRMED", "SEATED"],
    ).select_related("table").order_by("starts_at")
    return _page(
        request,
        "reservations",
        form=form,
        reservations=reservations,
        today_count=reservations.filter(starts_at__date=timezone.localdate()).count(),
        upcoming_count=reservations.count(),
        no_show_count=RestaurantReservation.objects.filter(
            business=business, starts_at__date=timezone.localdate(), status="NO_SHOW"
        ).count(),
    )


@login_required
@business_required
@require_POST
def reservation_action(request, reservation_id, action):
    business = _restaurant_business(request)
    with transaction.atomic():
        reservation = get_object_or_404(
            RestaurantReservation.objects.select_for_update().select_related("table"),
            business=business,
            pk=reservation_id,
        )
        if action == "confirm" and reservation.status == "PENDING":
            reservation.status = "CONFIRMED"
        elif action == "no-show" and reservation.status in {"PENDING", "CONFIRMED"}:
            if reservation.starts_at > timezone.now() - timedelta(minutes=15):
                messages.error(request, "A reservation can be marked no-show 15 minutes after its booking time.")
                return redirect("restaurant:reservations")
            reservation.status = "NO_SHOW"
        elif action == "cancel" and reservation.status in {"PENDING", "CONFIRMED"}:
            reservation.status = "CANCELLED"
        elif action == "seat" and reservation.status in {"PENDING", "CONFIRMED"}:
            if not reservation.table:
                messages.error(request, "Assign a table before seating this reservation.")
                return redirect("restaurant:reservations")
            table = RestaurantTable.objects.select_for_update().get(
                business=business, pk=reservation.table_id
            )
            if table.status not in {"AVAILABLE", "RESERVED"}:
                messages.error(request, "The assigned table is not available.")
                return redirect("restaurant:reservations")
            reservation.status = "SEATED"
            table.status = "OCCUPIED"
            table.seated_at = timezone.now()
            table.save(update_fields=["status", "seated_at", "updated_at"])
        else:
            messages.error(request, "That reservation action is not valid for its current status.")
            return redirect("restaurant:reservations")
        reservation.save(update_fields=["status", "updated_at"])
        if reservation.table and reservation.status in {"CANCELLED", "NO_SHOW"}:
            remaining_reservations = RestaurantReservation.objects.filter(
                business=business,
                table_id=reservation.table_id,
                starts_at__gte=timezone.now(),
                status__in=["PENDING", "CONFIRMED"],
            ).exists()
            if not remaining_reservations:
                RestaurantTable.objects.filter(
                    pk=reservation.table_id, business=business, status="RESERVED"
                ).update(status="AVAILABLE")
    messages.success(request, f"Reservation {reservation.code} updated.")
    return redirect("restaurant:reservations")


@login_required
@business_required
@never_cache
def kitchen_view(request):
    business = _restaurant_business(request)
    station = request.GET.get("station", "ALL").upper()
    if station != "ALL" and station not in KITCHEN_STATIONS:
        raise Http404
    open_sales = Sale.objects.filter(
        business=business,
        order_status__in=["PENDING", "PROCESSING"],
        sale_items__isnull=False,
    ).distinct()
    for sale in open_sales:
        KitchenTicket.objects.get_or_create(sale=sale)
    tickets = list(KitchenTicket.objects.filter(
        sale__business=business,
    ).exclude(status="COLLECTED").exclude(
        sale__order_status="CANCELLED"
    ).select_related("sale").prefetch_related("sale__sale_items__product"))
    for ticket in tickets:
        items = list(ticket.sale.sale_items.all())
        ticket.kitchen_items = []
        for item in items:
            metadata = item.product.metadata
            item_station = metadata.get("restaurant_station", "") if isinstance(metadata, dict) else ""
            if station == "ALL" or (isinstance(item_station, str) and item_station.upper() == station):
                ticket.kitchen_items.append(item)
    if station != "ALL":
        tickets = [ticket for ticket in tickets if ticket.kitchen_items]
    counts = {
        status: sum(ticket.status == status for ticket in tickets)
        for status, _ in KitchenTicket.STATUS_CHOICES
    }
    return _page(
        request,
        "kitchen",
        tickets=tickets,
        counts=counts,
        station=station,
        stations=KITCHEN_STATIONS,
    )


@login_required
@business_required
@require_POST
def kitchen_action(request, ticket_id, action):
    business = _restaurant_business(request)
    ticket = get_object_or_404(KitchenTicket, pk=ticket_id, sale__business=business)
    next_status = {"start": "COOKING", "ready": "READY", "collect": "COLLECTED"}.get(action)
    if not next_status:
        messages.error(request, "Unknown kitchen action.")
    else:
        try:
            with transaction.atomic():
                ticket = get_object_or_404(
                    KitchenTicket.objects.select_for_update(),
                    pk=ticket_id,
                    sale__business=business,
                )
                ticket.transition(next_status)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Order {ticket.sale.sale_number} marked {ticket.get_status_display().lower()}.")
    return redirect("restaurant:kitchen")


@login_required
@business_required
@never_cache
def menu_view(request):
    business = _restaurant_business(request)
    if request.method == "POST":
        if not _manager_required(request):
            return redirect("restaurant:menu")
        product = get_object_or_404(
            Product,
            business=business,
            pk=request.POST.get("product_id"),
        )
        station = request.POST.get("station", "").upper()
        if station and station not in KITCHEN_STATIONS:
            messages.error(request, "Choose a valid kitchen station.")
            return redirect("restaurant:menu")
        metadata = product.metadata if isinstance(product.metadata, dict) else {}
        if station:
            metadata["restaurant_station"] = station
        else:
            metadata.pop("restaurant_station", None)
        product.metadata = metadata
        product.is_active = request.POST.get("is_active") == "on"
        product.save(update_fields=["metadata", "is_active", "updated_at"])
        messages.success(request, f"{product.name} menu settings saved.")
        return redirect("restaurant:menu")
    products = Product.objects.filter(business=business).select_related("category").annotate(
        units_sold=Sum(
            "sale_items__quantity",
            filter=Q(
                sale_items__sale__sale_date__date__gte=timezone.localdate() - timedelta(days=30),
                sale_items__sale__sale_date__date__lte=timezone.localdate(),
            ),
        )
    ).order_by("name")
    return _page(
        request,
        "menu",
        products=products,
        active_count=products.filter(is_active=True).count(),
        product_count=products.count(),
        stations=KITCHEN_STATIONS,
    )


@login_required
@business_required
@never_cache
def ingredients_view(request):
    business = _restaurant_business(request)
    ingredients = Product.objects.filter(business=business, is_active=True).select_related(
        "category"
    ).order_by("name")
    low_stock = ingredients.filter(current_stock__lte=F("reorder_level"))
    return _page(
        request,
        "ingredients",
        ingredients=ingredients,
        ingredient_count=ingredients.count(),
        low_stock=low_stock,
    )


@login_required
@business_required
@never_cache
def recipes_view(request, recipe_id=None):
    business = _restaurant_business(request)
    recipe = None
    if recipe_id is not None:
        recipe = get_object_or_404(
            RestaurantRecipe.objects.select_related("menu_item").prefetch_related("ingredients__ingredient"),
            pk=recipe_id,
            menu_item__business=business,
        )
    if request.method == "POST":
        if not _manager_required(request):
            return redirect("restaurant:recipes")
        menu_item = get_object_or_404(
            restaurant_products(business), pk=request.POST.get("menu_item")
        )
        ingredient_ids = request.POST.getlist("ingredient")
        quantities = request.POST.getlist("quantity")
        try:
            prep_minutes = int(request.POST.get("preparation_minutes", "0"))
            yield_percent = Decimal(request.POST.get("yield_percent", "100"))
            waste_percent = Decimal(request.POST.get("waste_percent", "0"))
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter valid preparation, yield, and waste values.")
            return redirect("restaurant:recipes")
        if prep_minutes < 0 or yield_percent <= 0 or yield_percent > 100 or waste_percent < 0 or waste_percent >= 100:
            messages.error(request, "Prep time must be non-negative, yield must be above 0%, and waste must be below 100%.")
            return redirect("restaurant:recipes")
        if len(ingredient_ids) != len(quantities):
            messages.error(request, "Each recipe ingredient needs a quantity.")
            return redirect("restaurant:recipes")
        lines = []
        try:
            for product_id, raw_quantity in zip(ingredient_ids, quantities):
                ingredient = restaurant_products(business).get(pk=product_id)
                quantity = Decimal(raw_quantity)
                if quantity <= 0:
                    raise InvalidOperation
                lines.append((ingredient, quantity))
        except (Product.DoesNotExist, InvalidOperation):
            messages.error(request, "Choose valid ingredients and positive quantities from this business.")
            return redirect("restaurant:recipes")
        if len({ingredient.pk for ingredient, _ in lines}) != len(lines):
            messages.error(request, "Each ingredient can only be added once to a recipe.")
            return redirect("restaurant:recipes")
        try:
            with transaction.atomic():
                if recipe is None:
                    recipe = RestaurantRecipe(menu_item=menu_item)
                elif recipe.menu_item_id != menu_item.pk:
                    recipe.menu_item = menu_item
                recipe.preparation_minutes = prep_minutes
                recipe.method = request.POST.get("method", "").strip()
                recipe.yield_percent = yield_percent
                recipe.waste_percent = waste_percent
                recipe.save()
                recipe.ingredients.all().delete()
                RestaurantRecipeIngredient.objects.bulk_create([
                    RestaurantRecipeIngredient(
                        recipe=recipe,
                        ingredient=ingredient,
                        quantity=quantity,
                        unit=ingredient.unit,
                    )
                    for ingredient, quantity in lines
                ])
                recipe.sync_menu_item_cost()
        except IntegrityError:
            messages.error(request, "A recipe already exists for that menu item.")
            return redirect("restaurant:recipes")
        messages.success(request, f"Recipe for {menu_item.name} saved.")
        return redirect("restaurant:recipes")
    recipes = RestaurantRecipe.objects.filter(
        menu_item__business=business
    ).select_related("menu_item").prefetch_related("ingredients__ingredient")
    return _page(
        request,
        "recipes",
        recipe=recipe,
        recipes=recipes,
        products=restaurant_products(business),
        recipe_count=recipes.count(),
        missing_cost_count=recipes.filter(ingredients__isnull=True).distinct().count(),
    )


@login_required
@business_required
@require_POST
def recipe_delete(request, recipe_id):
    business = _restaurant_business(request)
    if not _manager_required(request):
        return redirect("restaurant:recipes")
    recipe = get_object_or_404(RestaurantRecipe, pk=recipe_id, menu_item__business=business)
    recipe.delete()
    messages.success(request, "Recipe deleted.")
    return redirect("restaurant:recipes")


@login_required
@business_required
@never_cache
def suppliers_view(request):
    business = _restaurant_business(request)
    form = RestaurantSupplierForm()
    if request.method == "POST":
        if not _manager_required(request):
            return redirect("restaurant:suppliers")
        form = RestaurantSupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.business = business
            try:
                supplier.save()
            except IntegrityError:
                form.add_error("name", "This supplier is already listed.")
            else:
                messages.success(request, f"Supplier {supplier.name} added.")
                return redirect("restaurant:suppliers")
    suppliers = RestaurantSupplier.objects.filter(business=business)
    return _page(
        request,
        "suppliers",
        form=form,
        suppliers=suppliers,
        catalog_suppliers=Product.objects.filter(
            business=business
        ).exclude(supplier_name="").values("supplier_name").annotate(
            product_count=Count("id")
        ).order_by("supplier_name"),
    )


@login_required
@business_required
@never_cache
def supplier_orders_view(request, supplier_id):
    business = _restaurant_business(request)
    supplier = get_object_or_404(RestaurantSupplier, business=business, pk=supplier_id)
    form = RestaurantPurchaseOrderForm()
    if request.method == "POST":
        if not _manager_required(request):
            return redirect("restaurant:supplier_orders", supplier_id=supplier.pk)
        form = RestaurantPurchaseOrderForm(request.POST)
        product_ids = request.POST.getlist("product")
        quantities = request.POST.getlist("quantity")
        costs = request.POST.getlist("unit_cost")
        if form.is_valid() and len(product_ids) == len(quantities) == len(costs):
            lines = []
            try:
                for product_id, raw_quantity, raw_cost in zip(product_ids, quantities, costs):
                    if not product_id and not raw_quantity and not raw_cost:
                        continue
                    product = restaurant_products(business).get(pk=product_id)
                    quantity = int(raw_quantity)
                    unit_cost = Decimal(raw_cost)
                    if quantity < 1 or unit_cost <= 0:
                        raise InvalidOperation
                    lines.append((product, quantity, unit_cost))
            except (Product.DoesNotExist, InvalidOperation, ValueError):
                form.add_error(None, "Choose saved stock items with a positive whole quantity and unit cost.")
            else:
                if not lines:
                    form.add_error(None, "Add at least one stock item to the purchase order.")
                elif len({product.pk for product, _, _ in lines}) != len(lines):
                    form.add_error(None, "Add each stock item only once to the order.")
                else:
                    with transaction.atomic():
                        order = RestaurantPurchaseOrder.objects.create(
                            business=business,
                            supplier=supplier,
                            expected_at=form.cleaned_data["expected_at"],
                            notes=form.cleaned_data["notes"],
                            created_by=request.user,
                        )
                        RestaurantPurchaseOrderLine.objects.bulk_create([
                            RestaurantPurchaseOrderLine(
                                purchase_order=order,
                                product=product,
                                quantity=quantity,
                                unit_cost=unit_cost,
                            )
                            for product, quantity, unit_cost in lines
                        ])
                    messages.success(request, f"Purchase order {order.order_number} saved.")
                    return redirect("restaurant:supplier_orders", supplier_id=supplier.pk)
        elif form.is_valid():
            form.add_error(None, "Each purchase-order line must include a product, quantity, and unit cost.")
    orders = RestaurantPurchaseOrder.objects.filter(
        business=business, supplier=supplier
    ).prefetch_related("lines__product")
    return _page(
        request,
        "supplier_orders",
        supplier=supplier,
        orders=orders,
        form=form,
        products=restaurant_products(business),
    )


@login_required
@business_required
@require_POST
def purchase_order_receive(request, order_id):
    business = _restaurant_business(request)
    if not _manager_required(request):
        return redirect("restaurant:suppliers")
    try:
        with transaction.atomic():
            order = get_object_or_404(
                RestaurantPurchaseOrder.objects.select_for_update().select_related("supplier"),
                business=business,
                pk=order_id,
            )
            if order.status != "ORDERED":
                messages.error(request, "Only an ordered purchase order can be received.")
                return redirect("restaurant:supplier_orders", supplier_id=order.supplier_id)
            for line in order.lines.select_related("product"):
                product = Product.objects.select_for_update().get(
                    business=business, pk=line.product_id
                )
                previous_stock = product.current_stock
                previous_cost = product.purchase_price
                InventoryTransaction.objects.create(
                    business=business,
                    product=product,
                    transaction_type="RECEIVED",
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    reference_type="PURCHASE_ORDER",
                    reference_id=str(order.pk),
                    reference_number=order.order_number,
                    notes=f"Received from {order.supplier.name}",
                    created_by=request.user,
                )
                product.refresh_from_db(fields=["current_stock"])
                if product.current_stock:
                    product.purchase_price = (
                        previous_cost * previous_stock + line.unit_cost * line.quantity
                    ) / product.current_stock
                product.supplier_name = order.supplier.name
                product.save(update_fields=["purchase_price", "supplier_name", "updated_at"])
            order.status = "RECEIVED"
            order.received_at = timezone.now()
            order.save(update_fields=["status", "received_at"])
    except Product.DoesNotExist:
        messages.error(request, "A stock item on this order no longer exists.")
        return redirect("restaurant:suppliers")
    messages.success(request, f"Purchase order {order.order_number} received and inventory updated.")
    return redirect("restaurant:supplier_orders", supplier_id=order.supplier_id)


@login_required
@business_required
@never_cache
def cash_drawer_view(request):
    business = _restaurant_business(request)
    shift = RestaurantCashShift.objects.filter(business=business, closed_at__isnull=True).first()
    open_form = RestaurantCashOpenForm()
    close_form = RestaurantCashCloseForm()
    movement_form = RestaurantCashMovementForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "open":
            open_form = RestaurantCashOpenForm(request.POST)
            if open_form.is_valid():
                try:
                    with transaction.atomic():
                        if RestaurantCashShift.objects.filter(
                            business=business, closed_at__isnull=True
                        ).exists():
                            raise IntegrityError
                        shift = RestaurantCashShift.objects.create(
                            business=business,
                            opened_by=request.user,
                            opening_cash=open_form.cleaned_data["opening_cash"],
                        )
                except IntegrityError:
                    messages.error(request, "There is already an open cash shift for this restaurant.")
                else:
                    messages.success(request, "Cash shift opened.")
                    return redirect("restaurant:cash_drawer")
        elif action == "close" and shift:
            close_form = RestaurantCashCloseForm(request.POST)
            if close_form.is_valid():
                shift.closing_cash = close_form.cleaned_data["closing_cash"]
                shift.closed_by = request.user
                shift.closed_at = timezone.now()
                shift.save(update_fields=["closing_cash", "closed_by", "closed_at"])
                messages.success(request, "Cash shift closed and reconciled.")
                return redirect("restaurant:cash_drawer")
        elif action == "movement" and shift:
            movement_form = RestaurantCashMovementForm(request.POST)
            if movement_form.is_valid():
                movement = movement_form.save(commit=False)
                movement.shift = shift
                movement.created_by = request.user
                movement.save()
                messages.success(request, "Cash movement recorded.")
                return redirect("restaurant:cash_drawer")
        else:
            messages.error(request, "Open a cash shift before recording movements or closing it.")
    if shift:
        shift = RestaurantCashShift.objects.prefetch_related("movements").get(pk=shift.pk)
    recent_shifts = RestaurantCashShift.objects.filter(business=business)[:10]
    return _page(
        request,
        "cash_drawer",
        shift=shift,
        open_form=open_form,
        close_form=close_form,
        movement_form=movement_form,
        recent_shifts=recent_shifts,
    )


@login_required
@business_required
@never_cache
def food_cost_view(request):
    business = _restaurant_business(request)
    recipes = list(
        RestaurantRecipe.objects.filter(menu_item__business=business)
        .select_related("menu_item")
        .prefetch_related("ingredients__ingredient")
    )
    food_cost_percentages = [
        recipe.portion_cost * Decimal("100") / recipe.menu_item.selling_price
        for recipe in recipes
        if recipe.menu_item.selling_price > 0 and recipe.portion_cost is not None
    ]
    total_cost = sum(
        (recipe.portion_cost for recipe in recipes if recipe.portion_cost is not None),
        Decimal("0"),
    )
    average_food_cost = (
        sum(food_cost_percentages, Decimal("0")) / len(food_cost_percentages)
        if food_cost_percentages else Decimal("0")
    )
    return _page(
        request,
        "food_cost",
        recipes=recipes,
        recipe_count=len(recipes),
        average_food_cost=average_food_cost,
        total_cost=total_cost,
    )
