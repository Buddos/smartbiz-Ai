from django import template

register = template.Library()


@register.simple_tag
def generic_business_shell_for(request):
    user = getattr(request, "user", None)
    business = getattr(user, "business", None)
    if not user or not user.is_authenticated or not business:
        return False

    match = request.resolver_match
    app_name = match.app_name
    url_name = match.url_name

    if business.business_type == "SALON":
        return (
            app_name != "salon"
            and url_name != "dashboard"
            and not (app_name == "products" and url_name == "list")
        )
    if business.business_type == "BARBER":
        return (
            app_name != "barber"
            and url_name != "dashboard"
            and not (app_name == "products" and url_name == "list")
        )
    return False


@register.simple_tag
def restaurant_business_shell_for(request):
    user = getattr(request, "user", None)
    business = getattr(user, "business", None)
    return bool(
        user
        and user.is_authenticated
        and business
        and business.business_type == "RESTAURANT"
        and request.resolver_match.url_name != "business_admin"
        and request.GET.get("from") != "admin"
    )
