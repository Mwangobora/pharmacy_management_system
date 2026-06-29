from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sales.models import Sale
from apps.users.permissions import HasViewPermissions

from .filters import DashboardFilterSerializer
from .finance_service import FinanceDashboardService
from .inventory_service import InventoryDashboardService
from .operations_service import OperationsDashboardService
from .overview_service import OverviewDashboardService
from .performance_service import PerformanceDashboardService
from .sales_service import SalesDashboardService


class DashboardBaseView(APIView):
    permission_classes = [IsAuthenticated, HasViewPermissions]
    required_permissions = []
    permission_mode = 'all'

    def get_required_permissions(self):
        return self.required_permissions

    def get_permission_mode(self):
        return self.permission_mode

    def get_filters(self, request):
        serializer = DashboardFilterSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data['resolved_filters']


class DashboardFiltersView(DashboardBaseView):
    required_permissions = [
        'dashboard.overview.view',
        'dashboard.sales.view',
        'dashboard.inventory.view',
        'dashboard.finance.view',
        'dashboard.operations.view',
        'dashboard.performance.view',
    ]
    permission_mode = 'any'

    def get(self, request):
        return Response({
            'payment_methods': [
                {'value': code, 'label': label}
                for code, label in Sale.PAYMENT_METHOD_CHOICES
            ],
            'cashiers': [
                {
                    'value': str(item['served_by_id']),
                    'label': item['served_by__username'],
                }
                for item in Sale.objects.filter(served_by__isnull=False)
                .values('served_by_id', 'served_by__username')
                .distinct()
                .order_by('served_by__username')
            ],
            'advanced_filters_available': ['cashier_id', 'payment_method'],
        })


class DashboardOverviewView(DashboardBaseView):
    required_permissions = ['dashboard.overview.view']

    def get(self, request):
        return Response(OverviewDashboardService.get_data(request.user, self.get_filters(request)))


class DashboardSalesView(DashboardBaseView):
    required_permissions = ['dashboard.sales.view']

    def get(self, request):
        return Response(SalesDashboardService.get_data(request.user, self.get_filters(request)))


class DashboardInventoryView(DashboardBaseView):
    required_permissions = ['dashboard.inventory.view']

    def get(self, request):
        return Response(InventoryDashboardService.get_data(request.user, self.get_filters(request)))


class DashboardFinanceView(DashboardBaseView):
    required_permissions = ['dashboard.finance.view']

    def get(self, request):
        return Response(FinanceDashboardService.get_data(request.user, self.get_filters(request)))


class DashboardOperationsView(DashboardBaseView):
    required_permissions = ['dashboard.operations.view']

    def get(self, request):
        return Response(OperationsDashboardService.get_data(request.user, self.get_filters(request)))


class DashboardPerformanceView(DashboardBaseView):
    required_permissions = ['dashboard.performance.view']

    def get(self, request):
        return Response(PerformanceDashboardService.get_data(request.user, self.get_filters(request)))


class DashboardAlertsView(DashboardOverviewView):
    def get(self, request):
        payload = OverviewDashboardService.get_data(request.user, self.get_filters(request))
        return Response({'alerts': payload['alerts'], 'period': payload['period']})


class DashboardRecentSalesView(DashboardOverviewView):
    def get(self, request):
        payload = OverviewDashboardService.get_data(request.user, self.get_filters(request))
        return Response({'recent_sales': payload['recent_sales'], 'period': payload['period']})
