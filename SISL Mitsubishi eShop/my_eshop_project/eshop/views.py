import os
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.core.mail import EmailMessage
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.template.response import TemplateResponse
from django.template.loader import render_to_string
import pdfkit  # Using pdfkit for PDF generation via wkhtmltopdf

from .models import Category, Banner, Brand, Product, Quotation
from .forms import BrandForm, ProductForm, QuotationHeaderForm, QuotationLineFormSet


def home_view(request):
    categories = Category.objects.filter(parent__isnull=True)
    banner = Banner.objects.first()
    vfd_products = Product.objects.filter(category__name__iexact='VFD').order_by('-id')[:8]
    plc_products = Product.objects.filter(category__name__iexact='PLC').order_by('-id')[:8]
    hmi_products = Product.objects.filter(category__name__iexact='HMI').order_by('-id')[:8]
    return render(request, 'home.html', {
        'categories': categories,
        'banner': banner,
        'vfd_products': vfd_products,
        'plc_products': plc_products,
        'hmi_products': hmi_products,
    })


def product_detail_view(request, sku):
    if not sku or sku.lower() == 'none':
        return redirect('home')
    product = get_object_or_404(Product, sku=sku)
    return render(request, 'product_detail.html', {'product': product})


def fx_series_view(request):
    """Placeholder view for FX Series."""
    return render(request, 'fx_series.html')


def vfd_view(request):
    """Placeholder view for VFD products."""
    return render(request, 'vfd.html')


def category_filter_view(request, cat_name):
    """Filters products by category."""
    products = Product.objects.filter(category__name__iexact=cat_name)
    return render(request, 'category_filter.html', {
        'cat_name': cat_name,
        'products': products,
    })


def brand_detail_view(request, brand_id):
    """Placeholder view for a specific brand."""
    brand = get_object_or_404(Brand, id=brand_id)
    return render(request, 'brand_detail.html', {'brand': brand})


def search_view(request):
    """Simple search functionality."""
    query = request.GET.get('q', '')
    products = Product.objects.filter(name__icontains=query) if query else []
    return render(request, 'search.html', {
        'query': query,
        'products': products,
    })


@login_required
def ask_for_discount_view(request, sku):
    """
    Handles the discount request form submission.
    After successful submission, sets the shareable PDF URL in the session and redirects to discount_submitted.
    """
    product = get_object_or_404(Product, sku=sku)
    
    # Build mapping: product ID -> original_price (as string)
    product_prices = {str(p.pk): str(p.original_price) for p in Product.objects.all()}
    product_prices_json = json.dumps(product_prices)
    
    if request.method == "POST":
        new_quote = Quotation()
        header_form = QuotationHeaderForm(request.POST, instance=new_quote)
        formset = QuotationLineFormSet(request.POST, instance=new_quote, prefix="lines")
        
        if header_form.is_valid() and formset.is_valid():
            new_quote = header_form.save(commit=False)
            new_quote.customer = request.user
            if not new_quote.customer_name and new_quote.phone_no:
                last6 = new_quote.phone_no[-6:] if len(new_quote.phone_no) >= 6 else new_quote.phone_no
                new_quote.customer_name = f"Customer #{last6}"
            
            generated_order_number = "ORD" + timezone.now().strftime("%Y%m%d%H%M%S")
            new_quote.order_number = generated_order_number
            new_quote.subject = (
                f"Discount Request for order no: {generated_order_number} on "
                f"{timezone.now().strftime('%Y-%m-%d')}"
            )
            new_quote.save()
            formset.save()
            if hasattr(new_quote, "compute_total"):
                new_quote.compute_total()
            
            # Generate PDF and send email using pdfkit (wkhtmltopdf)
            pdf_file_path, pdf_file_name = generate_pdf_file(new_quote)
            shareable_file_url = os.path.join(settings.MEDIA_URL, "quotations", pdf_file_name)
            subject_email = f"Discount request for {product.name}"
            body = (
                f"User {request.user} requested a multi-line discount.\n"
                f"Quotation ID: {new_quote.pk}\n\n"
                f"Please find the attached PDF for full details."
            )
            email = EmailMessage(
                subject=subject_email,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.DEFAULT_FROM_EMAIL],
            )
            email.attach_file(pdf_file_path)
            email.send()
            
            messages.success(
                request,
                f"Your discount request for Order No: {new_quote.order_number} has been successfully submitted! A PDF has been emailed."
            )
            # Save the shareable file URL in the session so discount_submitted_view can access it
            request.session['shareable_file_url'] = shareable_file_url
            return redirect("discount_submitted", quotation_id=new_quote.pk)
        else:
            return render(request, "new_discount.html", {
                "header_form": header_form,
                "formset": formset,
                "product_prices_json": product_prices_json,
            })
    else:
        new_quote = Quotation()
        header_form = QuotationHeaderForm(instance=new_quote)
        formset = QuotationLineFormSet(
            instance=new_quote,
            prefix="lines",
            initial=[{
                "product": product.pk,
                "quantity": 1,
                "unit_price": product.original_price,
                "discount_percent": 25
            }]
        )
        return render(request, "new_discount.html", {
            "header_form": header_form,
            "formset": formset,
            "product_prices_json": product_prices_json,
        })


def generate_pdf_file(quotation):
    """
    Generates a PDF file using wkhtmltopdf (via pdfkit).
    Renders an HTML template ('quotation_pdf.html') with the quotation data,
    saves the PDF under MEDIA_ROOT/quotations, and returns (pdf_file_path, pdf_file_name).
    """
    # Render the HTML template into a string
    html_string = render_to_string('quotation_pdf.html', {'quotation': quotation})
    
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    file_name = f"quotation_{quotation.pk}_{timestamp}.pdf"
    quotations_dir = os.path.join(settings.MEDIA_ROOT, "quotations")
    os.makedirs(quotations_dir, exist_ok=True)
    file_path = os.path.join(quotations_dir, file_name)
    
    # Configure pdfkit with the path to wkhtmltopdf executable (update the path if needed)
    config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
    
    # Generate the PDF file from the HTML string
    pdfkit.from_string(html_string, file_path, configuration=config)
    
    return file_path, file_name


@staff_member_required
def order_management_view(request):
    orders = Quotation.objects.all().order_by("-created_at")
    status_filter = request.GET.get("status")
    if status_filter:
        orders = orders.filter(status=status_filter)
    context = {"orders": orders}
    return TemplateResponse(request, "order_management.html", context)


def quotation_detail_view(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    return render(request, "quotation_detail.html", {
        "quotation": quotation,
        "lines": quotation.lines.all(),
    })


@login_required
def discount_submitted_view(request, quotation_id):
    """
    Displays the success page with quotation details.
    Retrieves the quotation by ID, and attempts to get the product (from the first line)
    and shareable_file_url (stored in session).
    """
    quotation = get_object_or_404(Quotation, pk=quotation_id)
    product = quotation.lines.first().product if quotation.lines.exists() else None
    shareable_file_url = request.session.get('shareable_file_url', None)
    return render(request, "discount_submitted.html", {
         "quotation": quotation,
         "product": product,
         "shareable_file_url": shareable_file_url,
    })
