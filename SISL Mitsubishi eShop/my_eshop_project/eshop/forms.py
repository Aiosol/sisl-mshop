from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from .models import Brand, Product, Quotation, QuotationLine
import sys

ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif']


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'logo', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo:
            if logo.content_type not in ALLOWED_IMAGE_TYPES:
                raise ValidationError('Only JPEG, PNG, or GIF files are allowed for logos.')
        return logo


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['brand', 'name', 'description', 'original_price', 'sku', 'image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.content_type not in ALLOWED_IMAGE_TYPES:
                raise ValidationError('Only JPEG, PNG, or GIF files are allowed for product images.')
        return image


class ProductSelectWidget(forms.Select):
    """
    Custom widget to attach `data-price` to <option> for auto-filling
    the unit_price in the QuotationLine form via JavaScript.
    """
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value not in [None, '']:
            try:
                # Retrieve the product so we can attach its original_price
                product = self.choices.queryset.get(pk=value)
                option['attrs']['data-price'] = str(product.original_price)
                sys.stderr.write(f"ProductSelectWidget: Added data-price={product.original_price} for product pk={value}\n")
            except Exception as e:
                sys.stderr.write(f"ProductSelectWidget error for product pk={value}: {e}\n")
        return option


class QuotationHeaderForm(forms.ModelForm):
    """
    Header form for Quotation, with Email and Delivery Address as optional fields.
    """
    phone_no = forms.CharField(
        required=True,
        label="Phone No",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    customer_name = forms.CharField(
        required=False,
        label="Customer Name",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.CharField(
        required=False,
        label="Email (Optional)",
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    delivery_address = forms.CharField(
        required=False,
        label="Delivery Address (Optional)",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    subject = forms.CharField(
        required=False,
        label="Subject",
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'})
    )

    class Meta:
        model = Quotation
        fields = [
            'customer_name',
            'phone_no',
            'email',
            'delivery_address',
            'subject',
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class QuotationLineForm(forms.ModelForm):
    """
    Inline form for each QuotationLine.
    - Auto-fill unit_price from product original_price (via JS, and as a fallback server-side).
    - discount_percent defaults to 25 (read-only).
    - unit_price is read-only.
    - quantity is editable.
    """
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
        Server-side fallback: if the unit_price field is blank or zero,
        automatically set it to the product's original_price.
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
