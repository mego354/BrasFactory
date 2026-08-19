def navigation(request):
    """Inject navigation items and user context into every template."""
    nav_items = [
        {'url': 'production:dashboard', 'label': 'الرئيسية', 'icon': 'home'},
        {'url': 'catalog:model_list', 'label': 'الموديلات', 'icon': 'cube'},
        {'url': 'production:entry', 'label': 'الإنتاج', 'icon': 'clipboard-list'},
        {'url': 'workers:list', 'label': 'العمال', 'icon': 'user-group'},
        {'url': 'reports:index', 'label': 'التقارير', 'icon': 'chart-bar'},
        {'url': 'catalog:settings_index', 'label': 'الإعدادات', 'icon': 'cog'},
    ]
    return {
        'nav_items': nav_items,
    }
