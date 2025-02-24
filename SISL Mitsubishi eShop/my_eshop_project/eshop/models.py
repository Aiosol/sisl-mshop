from django.db import models
from django.contrib.auth.models import User

# Order status choices for managing orders
class OrderStatus(models.TextChoices):
    PENDING = 'P', 'Pending'
    CONFIRMED = 'C', 'Confirmed'
    CANCELED = 'X', 'Canceled'
    DELIVERED = 'D', 'Delivered'


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    parent = models.ForeignKey(
        'self',
        related_name='children',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    def __str__(self):
        return self.name


class Banner(models.Model):
    title = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to='banners/', null=True, blank=True)

    def __str__(self):
        return self.title if self.title else "Banner"


class Brand(models.Model):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='brands/logos/', null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE)
    name = models.CharField("Model Name", max_length=255, unique=True)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=50, unique=True)
    image = models.ImageField(upload_to='products/')
    country_of_origin = models.CharField(max_length=100)

    description = models.TextField(blank=True, null=True)
    discounted_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        blank=True, null=True
    )

    # Example ManyToMany fields
    related_products = models.ManyToManyField(
        'self',
        symmetrical=False,
        blank=True,
        related_name='linked_products'
    )
    compatible_modules = models.ManyToManyField(
        'self',
        symmetrical=False,
        blank=True,
        related_name='plc_or_hmi_compatible'
    )

    def __str__(self):
        return self.name


class Quotation(models.Model):
    """
    Quotation model with phone_no, customer_name, email, delivery_address, etc.
    """
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    order_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    subject = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(
        max_length=1,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING
    )

    # Storing customer details directly on the Quotation model.
    phone_no = models.CharField(max_length=20, blank=True, null=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    delivery_address = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Quotation #{self.pk} for {self.customer or 'Anonymous'}"

    def compute_total(self):
        """
        Sums the line_total of each related QuotationLine,
        then updates total_amount.
        """
        total = sum(line.line_total() for line in self.lines.all())
        self.total_amount = total
        self.save(update_fields=['total_amount'])

    # Optional helper methods for use in templates
    def get_customer_display_name(self):
        if self.customer_name:
            return self.customer_name
        elif self.customer:
            return self.customer.get_full_name() or self.customer.username
        return "Anonymous"

    def get_customer_email(self):
        if self.email:
            return self.email
        elif self.customer:
            return self.customer.email
        return ""

    def get_phone_no(self):
        return self.phone_no or "N/A"

    def get_delivery_address(self):
        return self.delivery_address or "N/A"


class QuotationLine(models.Model):
    """
    Represents one line item in a Quotation.
    """
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    description = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=25)

    def save(self, *args, **kwargs):
        if self.product and (not self.unit_price or self.unit_price == 0):
            self.unit_price = self.product.original_price
        super().save(*args, **kwargs)

    def line_total(self):
        subtotal = self.quantity * self.unit_price
        discount_amount = subtotal * (self.discount_percent / 100)
        return subtotal - discount_amount

    def __str__(self):
        return f"Line {self.pk} in Quotation #{self.quotation.pk}"
