from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('product/<str:sku>/', views.product_detail_view, name='product_detail'),
    path('fx-series/', views.fx_series_view, name='fx_series'),
    path('vfd/', views.vfd_view, name='vfd'),
    path('category/<str:cat_name>/', views.category_filter_view, name='category_filter'),
    path('brand/<int:brand_id>/', views.brand_detail_view, name='brand_detail'),
    path('search/', views.search_view, name='search'),
    path('ask-discount/<str:sku>/', views.ask_for_discount_view, name='ask_for_discount'),
    path('quotation/<int:pk>/', views.quotation_detail_view, name='quotation_detail'),
    path('order-management/', views.order_management_view, name='order_management'),
    path('discount-submitted/', views.discount_submitted_view, name='discount_submitted'),
    path('discount-submitted/<int:quotation_id>/', views.discount_submitted_view, name='discount_submitted'),
]
