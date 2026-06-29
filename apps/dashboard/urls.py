from django.urls import path

from .views import (
    DashboardAlertsView,
    DashboardFiltersView,
    DashboardFinanceView,
    DashboardInventoryView,
    DashboardOperationsView,
    DashboardOverviewView,
    DashboardPerformanceView,
    DashboardRecentSalesView,
    DashboardSalesView,
)


urlpatterns = [
    path('filters/', DashboardFiltersView.as_view(), name='dashboard-filters'),
    path('overview/', DashboardOverviewView.as_view(), name='dashboard-overview'),
    path('sales/', DashboardSalesView.as_view(), name='dashboard-sales'),
    path('inventory/', DashboardInventoryView.as_view(), name='dashboard-inventory'),
    path('finance/', DashboardFinanceView.as_view(), name='dashboard-finance'),
    path('operations/', DashboardOperationsView.as_view(), name='dashboard-operations'),
    path('performance/', DashboardPerformanceView.as_view(), name='dashboard-performance'),
    path('alerts/', DashboardAlertsView.as_view(), name='dashboard-alerts'),
    path('recent-sales/', DashboardRecentSalesView.as_view(), name='dashboard-recent-sales'),
]
