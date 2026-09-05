def business_context(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"current_business": None, "user_permissions": {}}
    return {
        "current_business": getattr(request.user, "business", None),
        "user_permissions": request.user.get_user_permissions_list(),
    }
