# eshop/admin.py

import json
import requests
import sys

from django import forms
from django.forms import inlineformset_factory  # Ensure this import is present
from django.contrib import admin, messages
from django.db import IntegrityError
from django.template.response import TemplateResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import path
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    Category, Banner, Brand, Product,
    Quotation, QuotationLine, OrderStatus
)
from .forms import BrandForm, ProductForm, QuotationHeaderForm

###############################################
# CATEGORY, BANNER, BRAND, & PRODUCT ADMIN
###############################################

class SubCategoryInline(admin.TabularInline):
    model = Category
    fk_name = 'parent'
    extra = 1

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    inlines = [SubCategoryInline]

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title',)

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductForm
    list_display = (
        'name',
        'sku',
        'original_price',
        'discounted_price',
        'category',
        'brand',
        'clone_link'
    )
    filter_horizontal = ('related_products', 'compatible_modules')
    fieldsets = (
        ("General Mandatory Fields", {
            'fields': (
                "category",
                "brand",
                "name",
                "description",
                "original_price",
                "discounted_price",
                "sku",
                "image",
                "country_of_origin",
            )
        }),
    )
    change_form_template = "admin/eshop/product/change_form.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:product_id>/clone/',
                self.admin_site.admin_view(self.clone_view),
                name='eshop_product_clone'
            ),
        ]
        return custom_urls + urls

    def clone_view(self, request, product_id):
        new_model_name = request.GET.get('model_name', '').strip()
        new_sku = request.GET.get('sku', '').strip()

        if not new_model_name:
            messages.error(request, "Model Name is required to clone the product.")
            return redirect(request.META.get('HTTP_REFERER', 'admin:index'))
        if not new_sku:
            messages.error(request, "SKU is required to clone the product.")
            return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

        if Product.objects.filter(name=new_model_name).exists():
            messages.error(
                request,
                f"A product with Model Name '{new_model_name}' already exists."
            )
            return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

        if Product.objects.filter(sku=new_sku).exists():
            messages.error(
                request,
                f"A product with SKU '{new_sku}' already exists."
            )
            return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

        original_product = get_object_or_404(Product, pk=product_id)
        old_related = original_product.related_products.all()
        old_modules = original_product.compatible_modules.all()

        # Duplicate
        original_product.pk = None
        original_product.name = new_model_name
        original_product.sku = new_sku

        try:
            original_product.save()
        except IntegrityError as e:
            messages.error(request, f"Integrity error while saving clone: {str(e)}")
            return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

        # Re-attach many-to-many relationships
        original_product.related_products.set(old_related)
        original_product.compatible_modules.set(old_modules)

        messages.success(
            request,
            f"Product cloned successfully with Model Name '{new_model_name}' "
            f"and SKU '{new_sku}'."
        )
        return redirect(f'../../{original_product.pk}/change/')

    def clone_link(self, obj):
        url = f"{obj.pk}/clone/"
        return format_html(
            '<a href="{}" onclick="return promptCloneNameAndSKU(this);">Clone</a>',
            url
        )
    clone_link.short_description = "Clone"

###############################################
# ACCOUNTING API HELPER FUNCTIONS
###############################################

def _compute_final_customer_name(q):
    if q.customer_name:
        return q.customer_name
    phone = q.phone_no or ""
    last6 = phone[-6:] if len(phone) >= 6 else phone
    return f"Customer # {last6}"

def create_customer_in_accounting(order):
    final_name = _compute_final_customer_name(order)
    billing_addr = ""
    delivery_addr = ""
    email_value = ""

    custom_string_dict = {}
    if order.phone_no:
        custom_string_dict["f732a914-f5ca-4e3b-bba2-70198f5e6b75"] = order.phone_no

    payload = {
        "Name": final_name,
        "BillingAddress": billing_addr,
        "DeliveryAddress": delivery_addr,
        "Email": email_value,
        "CustomFields": {},
        "CustomFields2": {
            "Strings": custom_string_dict,
            "Decimals": {},
            "Dates": {},
            "Booleans": {},
            "StringArrays": {}
        }
    }

    url = "https://acc.aiosol.io/api2/customer-form"
    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': 'CgRERU1PEhIJAnrzI5egzkURl2LZU3OI5xUaEgndVzUL4yiPQRGt0qpiCi1Wcg=='
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    if resp.status_code in [200, 201]:
        data = resp.json()
        return data.get("Key")
    else:
        raise Exception(f"Error creating customer: {resp.text}")

def get_inventory_item_key(sku):
    url = "https://acc.aiosol.io/api2/inventory-items/"
    headers = {
        'Accept': 'application/json',
        'X-API-KEY': 'CgRERU1PEhIJAnrzI5egzkURl2LZU3OI5xUaEgndVzUL4yiPQRGt0qpiCi1Wcg=='
    }
    response = requests.get(url, headers=headers)
    if response.status_code in [200, 201]:
        data = response.json()
        if isinstance(data, dict) and "inventoryItems" in data:
            inventory_items = data["inventoryItems"]
        elif isinstance(data, list):
            inventory_items = data
        else:
            raise Exception(f"Unexpected inventory items format: {data}")

        for item in inventory_items:
            if str(item.get("itemCode", "")) == str(sku):
                return item.get("key")
        raise Exception(
            f"Error finding inventory item for SKU {sku}: not found in accounting."
        )
    else:
        raise Exception(f"Error retrieving inventory items: {response.text}")

def create_sales_order_in_accounting(customer_key, order):
    lines_payload = []
    has_discount = False

    for line in order.lines.all():
        discount_val = float(line.discount_percent or 0)
        if discount_val > 0:
            has_discount = True

        item_key = get_inventory_item_key(line.product.sku)
        line_payload = {
            "Item": item_key,
            "LineDescription": line.product.name,
            "CustomFields": {},
            "CustomFields2": {
                "Strings": {},
                "Decimals": {},
                "Dates": {},
                "Booleans": {},
                "StringArrays": {}
            },
            "Qty": float(line.quantity),
            "SalesUnitPrice": float(line.unit_price),
            "DiscountPercentage": discount_val
        }
        lines_payload.append(line_payload)

    payload = {
        "Date": order.created_at.strftime("%Y-%m-%dT00:00:00"),
        "Reference": order.order_number,
        "Customer": customer_key,
        "Lines": lines_payload,
        "Discount": has_discount,
        "SalesOrderFooters": [],
        "CustomFields": {},
        "CustomFields2": {
            "Strings": {},
            "Decimals": {},
            "Dates": {},
            "Booleans": {},
            "StringArrays": {}
        }
    }

    url = "https://acc.aiosol.io/api2/sales-order-form"
    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': 'CgRERU1PEhIJAnrzI5egzkURl2LZU3OI5xUaEgndVzUL4yiPQRGt0qpiCi1Wcg=='
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    if resp.status_code in [200, 201]:
        data = resp.json()
        return data.get("Key")
    else:
        raise Exception(f"Error creating sales order: {resp.text}")

###############################################
# AUTO-FILL PRICE LOGIC FOR QuotationLine
###############################################

# 1. Custom widget to attach data-price on <option>
class ProductSelectWidget(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            # Extract the actual value in case it's a ModelChoiceIteratorValue
            actual_value = getattr(value, 'value', value)
            try:
                product = self.choices.queryset.get(pk=actual_value)
                option['attrs']['data-price'] = str(product.original_price or 0)
            except Product.DoesNotExist:
                pass
        return option

# 2. Custom form for QuotationLine with server-side fallback
class QuotationLineForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=ProductSelectWidget(attrs={'class': 'form-select product-select'})
    )
    class Meta:
        model = QuotationLine
        fields = ['product', 'description', 'quantity', 'unit_price', 'discount_percent']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set discount to 25 if it's a new line
        if not self.instance.pk:
            self.fields['discount_percent'].initial = 25

        # Make discount & unit_price read-only
        self.fields['discount_percent'].widget.attrs.update({
            'class': 'form-control discount-input',
            'readonly': True,
            'style': 'background-color: #e9ecef;'
        })
        self.fields['unit_price'].widget.attrs.update({
            'class': 'form-control unit-price-input',
            'readonly': True,
            'style': 'background-color: #e9ecef;'
        })
        # Other fields remain editable
        self.fields['description'].widget.attrs.update({'class': 'form-control'})
        self.fields['quantity'].widget.attrs.update({'class': 'form-control quantity-input'})

    def clean(self):
        """
        Server-side fallback: If the unit_price is empty or zero,
        auto-fill it from the selected product's original_price.
        """
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        unit_price = cleaned_data.get("unit_price")
        if product and (unit_price is None or unit_price == 0):
            cleaned_data["unit_price"] = product.original_price
        return cleaned_data

QuotationLineFormSet = inlineformset_factory(
    Quotation,
    QuotationLine,
    form=QuotationLineForm,
    extra=1,
    can_delete=True
)

# 3. Inline referencing the custom form + loading custom JS
class QuotationLineInline(admin.TabularInline):
    model = QuotationLine
    form = QuotationLineForm
    extra = 0
    # Optionally, set prefix if needed:
    # prefix = "lines"  # Uncomment if you want to force the prefix to "lines"
    
    # Permanently remove the "Add another Quotation line" link
    def has_add_permission(self, request, obj):
        return False
    
    class Media:
        js = ('js/product_auto_price.js',)

###############################################
# QUOTATION ADMIN & ORDER MANAGEMENT
###############################################

def confirm_orders_in_accounting(modeladmin, request, queryset):
    for order in queryset:
        if order.status != OrderStatus.CONFIRMED:
            try:
                customer_key = create_customer_in_accounting(order)
                so_key = create_sales_order_in_accounting(customer_key, order)
                order.status = OrderStatus.CONFIRMED
                order.save(update_fields=['status'])
                messages.success(
                    request,
                    f"Order {order.order_number} confirmed. Sales Order Key: {so_key}"
                )
            except Exception as e:
                messages.error(
                    request,
                    f"Error posting order {order.order_number} to accounting: {str(e)}"
                )

confirm_orders_in_accounting.short_description = "Confirm selected orders in Accounting"

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = (
        'order_number',
        'customer_name',
        'phone_no',
        'created_at',
        'total_amount',
        'status',
    )
    list_filter = ('status', 'created_at')
    search_fields = (
        'order_number',
        'customer_name',
        'phone_no',
        'customer__username',
        'customer__email',
    )
    actions = [confirm_orders_in_accounting]
    
    inlines = [QuotationLineInline]

    fieldsets = (
        ('Customer Info', {
            'fields': ('customer', 'customer_name', 'phone_no', 'email', 'delivery_address')
        }),
        ('Order Info', {
            'fields': ('order_number', 'subject', 'status', 'notes')
        }),
        ('Totals', {
            'fields': ('total_amount', 'created_at')
        }),
    )
    readonly_fields = ('created_at', 'total_amount',)

    def save_model(self, request, obj, form, change):
        if not obj.order_number:
            obj.order_number = "ORD" + timezone.now().strftime("%Y%m%d%H%M%S")
            if not obj.subject:
                obj.subject = (
                    f"Discount Request for order no: {obj.order_number} on "
                    f"{timezone.now().strftime('%Y-%m-%d')}"
                )
        old_status = None
        if obj.pk:
            old_instance = Quotation.objects.filter(pk=obj.pk).first()
            if old_instance:
                old_status = old_instance.status
        super().save_model(request, obj, form, change)
        if old_status != OrderStatus.CONFIRMED and obj.status == OrderStatus.CONFIRMED:
            try:
                ckey = create_customer_in_accounting(obj)
                so_key = create_sales_order_in_accounting(ckey, obj)
                messages.success(
                    request,
                    f"Successfully posted Quotation {obj.order_number} to accounting. SalesOrderKey={so_key}"
                )
            except Exception as e:
                obj.status = old_status
                obj.save(update_fields=['status'])
                messages.error(
                    request,
                    f"Error posting order {obj.order_number} to accounting: {str(e)}"
                )

@admin.register(QuotationLine)
class QuotationLineAdmin(admin.ModelAdmin):
    list_display = ('quotation', 'product', 'quantity', 'unit_price', 'discount_percent')
