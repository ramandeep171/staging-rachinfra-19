// ========================================
// RACH INFRA - Batching Plant Rental
// Interactive JavaScript
// ========================================

document.addEventListener('DOMContentLoaded', function () {

    const batchingPlantPage = document.querySelector('.batching-plant-page');

    const isInvalidAnchorHref = (href) => {
        const cleanHref = (href || '').trim();
        return !cleanHref || cleanHref === '#' || cleanHref === '# ' || cleanHref === '##';
    };

    if (batchingPlantPage) {
        // Limit "#" blocking to batching plant content so global navigation keeps working
        batchingPlantPage.addEventListener('click', function (e) {
            const a = e.target.closest('a');
            if (!a || !batchingPlantPage.contains(a)) {
                return;
            }

            if (isInvalidAnchorHref(a.getAttribute('href'))) {
                e.preventDefault();
                e.stopImmediatePropagation();
            }
        }, true);
    }

    // ========================================
    // Initialize AOS (Animate On Scroll)
    // ========================================
    if (typeof AOS !== 'undefined') {
        AOS.init({
            duration: 800,
            once: true,
            offset: 100,
            easing: 'ease-in-out'
        });
    }

    // ========================================
    // Smooth Scrolling for Anchor Links
    // ========================================
    if (batchingPlantPage) {
        // Smooth scroll for only real anchors within batching plant page
        batchingPlantPage.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {

                let href = (this.getAttribute('href') || '').trim();

                // Skip malformed/empty anchors → prevent Odoo's bad handler
                if (isInvalidAnchorHref(href) || href.length <= 1) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    return false;
                }

                // Clean href → remove leading "#"
                let targetId = href.replace(/^#+/, '').trim();
                if (!targetId) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    return false;
                }

                // Safe element lookup
                let target = document.getElementById(targetId);
                if (!target) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    return false;
                }

                // Execute smooth scroll
                e.preventDefault();
                e.stopImmediatePropagation();

                const offsetTop = target.offsetTop - 80;
                window.scrollTo({
                    top: offsetTop,
                    behavior: 'smooth'
                });
            });
        });
    }


    // ========================================
    // Plant Capacity Selector
    // ========================================
    const capacityButtons = document.querySelectorAll('.capacity-btn');
    const capacityDetails = document.querySelectorAll('.capacity-details');

    capacityButtons.forEach(button => {
        button.addEventListener('click', function () {
            const capacity = this.getAttribute('data-capacity');

            // Remove active class from all buttons
            capacityButtons.forEach(btn => btn.classList.remove('active'));

            // Add active class to clicked button
            this.classList.add('active');

            // Hide all capacity details
            capacityDetails.forEach(detail => detail.classList.remove('active'));

            // Show selected capacity details
            const selectedDetail = document.getElementById(capacity);
            if (selectedDetail) {
                selectedDetail.classList.add('active');

                // Scroll to capacity content
                setTimeout(() => {
                    selectedDetail.scrollIntoView({
                        behavior: 'smooth',
                        block: 'nearest'
                    });
                }, 100);
            }
        });
    });

    // ========================================
    // Production Chart (Chart.js)
    // ========================================
    const chartCanvas = document.getElementById('productionChart');
    if (chartCanvas && typeof Chart !== 'undefined') {
        const ctx = chartCanvas.getContext('2d');

        const gradient1 = ctx.createLinearGradient(0, 0, 0, 300);
        gradient1.addColorStop(0, 'rgba(255, 107, 53, 0.5)');
        gradient1.addColorStop(1, 'rgba(255, 107, 53, 0.1)');

        const gradient2 = ctx.createLinearGradient(0, 0, 0, 300);
        gradient2.addColorStop(0, 'rgba(37, 99, 235, 0.5)');
        gradient2.addColorStop(1, 'rgba(37, 99, 235, 0.1)');

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                datasets: [
                    {
                        label: 'Production (m³)',
                        data: [220, 235, 245, 230, 250, 245, 245],
                        borderColor: '#FF6B35',
                        backgroundColor: gradient1,
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#FF6B35',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointRadius: 5,
                        pointHoverRadius: 7
                    },
                    {
                        label: 'Target (m³)',
                        data: [240, 240, 240, 240, 240, 240, 240],
                        borderColor: '#2563EB',
                        backgroundColor: gradient2,
                        borderWidth: 3,
                        borderDash: [10, 5],
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#2563EB',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointRadius: 5,
                        pointHoverRadius: 7
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 15,
                            font: {
                                size: 13,
                                family: 'Inter'
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: {
                            size: 14,
                            family: 'Inter'
                        },
                        bodyFont: {
                            size: 13,
                            family: 'Inter'
                        },
                        displayColors: true,
                        borderColor: 'rgba(255, 255, 255, 0.2)',
                        borderWidth: 1
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            font: {
                                size: 12,
                                family: 'Inter'
                            }
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            font: {
                                size: 12,
                                family: 'Inter'
                            },
                            callback: function (value) {
                                return value + ' m³';
                            }
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                }
            }
        });
    }

    // ========================================
    // Contact Form Handling
    // ========================================
    const contactForm = document.getElementById('contactForm');
    const formSuccess = document.getElementById('formSuccess');
    const inventoryMode = document.getElementById('x_inventory_mode');
    const gradeWrapper = document.getElementById('gradeWrapper');
    const successMessage = document.getElementById('successMessage');
    const quoteNumber = document.getElementById('quoteNumber');
    const quoteDownload = document.getElementById('quoteDownload');
    const newQuoteRequest = document.getElementById('newQuoteRequest');
    const quotePreview = document.getElementById('quotePreview');
    const quotePreviewFrame = document.getElementById('quotePreviewFrame');

    const toggleGradeField = () => {
        if (!inventoryMode || !gradeWrapper) {
            return;
        }
        gradeWrapper.style.display = inventoryMode.value === 'with_inventory' ? 'block' : 'none';
    };

    if (inventoryMode) {
        inventoryMode.addEventListener('change', toggleGradeField);
        toggleGradeField();
    }

    const resetSuccessState = () => {
        if (quoteNumber) {
            quoteNumber.textContent = '';
            quoteNumber.classList.remove('show');
        }
        if (quoteDownload) {
            quoteDownload.classList.remove('show');
            quoteDownload.removeAttribute('href');
            quoteDownload.removeAttribute('download');
        }
        if (quotePreview) {
            quotePreview.classList.remove('show');
        }
        if (quotePreviewFrame) {
            quotePreviewFrame.removeAttribute('src');
        }
    };

    if (newQuoteRequest && contactForm) {
        newQuoteRequest.addEventListener('click', () => {
            contactForm.reset();
            toggleGradeField();
            resetSuccessState();
            formSuccess.classList.remove('show');
            contactForm.style.display = 'block';
            contactForm.scrollIntoView({ behavior: 'smooth' });
        });
    }

    if (contactForm) {
        contactForm.addEventListener('submit', function (e) {
            e.preventDefault();

            // Get form data
            const formData = {
                partner_name: document.getElementById('partner_name').value.trim(),
                company_name: document.getElementById('company_name').value.trim(),
                email: document.getElementById('email').value.trim(),
                phone: document.getElementById('phone').value.trim(),
                gear_service_type: document.getElementById('gear_service_type').value,
                gear_capacity_id: document.getElementById('gear_capacity_id').value,
                mgq_monthly: document.getElementById('mgq_monthly').value,
                gear_expected_production_qty: document.getElementById('gear_expected_production_qty').value,
                x_inventory_mode: inventoryMode ? inventoryMode.value : '',
                gear_design_mix_id: document.getElementById('gear_design_mix_id').value,
                gear_material_area_id: document.getElementById('gear_material_area_id').value,
                gear_project_duration_years: document.getElementById('gear_project_duration_years').value,
                gear_civil_scope: document.getElementById('gear_civil_scope').value,
                note: document.getElementById('note').value,
                gear_transport_opt_in: document.querySelector("input[name='gear_transport_opt_in']").checked,
                gear_transport_per_cum: document.querySelector("input[name='gear_transport_per_cum']").value,
                gear_pumping_opt_in: document.querySelector("input[name='gear_pumping_opt_in']").checked,
                gear_pump_per_cum: document.querySelector("input[name='gear_pump_per_cum']").value,
                gear_manpower_opt_in: document.querySelector("input[name='gear_manpower_opt_in']").checked,
                gear_manpower_per_cum: document.querySelector("input[name='gear_manpower_per_cum']").value,
                gear_diesel_opt_in: document.querySelector("input[name='gear_diesel_opt_in']").checked,
                gear_diesel_per_cum: document.querySelector("input[name='gear_diesel_per_cum']").value,
                gear_jcb_opt_in: document.querySelector("input[name='gear_jcb_opt_in']").checked,
                gear_jcb_monthly: document.querySelector("input[name='gear_jcb_monthly']").value,
            };

            // Validate required fields
            if (!formData.partner_name || !formData.email || !formData.phone || !formData.gear_service_type || !formData.gear_capacity_id || !formData.x_inventory_mode) {
                alert('Please fill in all required fields.');
                return;
            }

            if (formData.x_inventory_mode === 'with_inventory' && !formData.gear_design_mix_id) {
                alert('Please select a grade mix for inventory mode.');
                return;
            }

            // Email validation
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(formData.email)) {
                alert('Please enter a valid email address.');
                return;
            }

            // Show loading state
            const submitBtn = contactForm.querySelector('.btn-submit');
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
            submitBtn.disabled = true;

            // Send JSON-RPC request
            fetch('/batching-plant/submit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: formData,
                    id: Date.now()
                })
            })
                .then(response => response.json())
                .then(data => {
                    const result = data.result;
                    if (result && result.success) {
                        contactForm.style.display = 'none';
                        formSuccess.classList.add('show');
                        formSuccess.scrollIntoView({ behavior: 'smooth' });

                        submitBtn.innerHTML = originalText;
                        submitBtn.disabled = false;

                        contactForm.reset();
                        toggleGradeField();

                        if (successMessage && result.sale_order_name) {
                            successMessage.textContent = `Quotation ${result.sale_order_name} is ready. A copy has been emailed to you as well.`;
                        }

                        if (quoteNumber && result.sale_order_name) {
                            quoteNumber.textContent = `Quotation Number: ${result.sale_order_name}`;
                            quoteNumber.classList.add('show');
                        }

                        if (quoteDownload && result.pdf_content) {
                            const pdfFilename = result.pdf_filename || `${result.sale_order_name || 'quotation'}.pdf`;
                            const dataUrl = `data:application/pdf;base64,${result.pdf_content}`;
                            quoteDownload.href = dataUrl;
                            quoteDownload.download = pdfFilename;
                            quoteDownload.classList.add('show');

                            if (quotePreview && quotePreviewFrame) {
                                quotePreviewFrame.src = dataUrl;
                                quotePreview.classList.add('show');
                            }

                            const tempLink = document.createElement('a');
                            tempLink.href = dataUrl;
                            tempLink.download = pdfFilename;
                            tempLink.style.display = 'none';
                            document.body.appendChild(tempLink);
                            tempLink.click();
                            document.body.removeChild(tempLink);
                        } else {
                            if (quoteDownload) {
                                quoteDownload.classList.remove('show');
                                quoteDownload.removeAttribute('href');
                                quoteDownload.removeAttribute('download');
                            }
                            if (quotePreview && quotePreviewFrame) {
                                quotePreview.classList.remove('show');
                                quotePreviewFrame.removeAttribute('src');
                            }
                        }
                    } else {
                        // Handle error
                        console.error('Error:', data.error || data.result?.error);
                        alert('An error occurred. Please try again.');
                        submitBtn.innerHTML = originalText;
                        submitBtn.disabled = false;
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('An error occurred. Please try again.');
                    submitBtn.innerHTML = originalText;
                    submitBtn.disabled = false;
                });
        });
    }

    // ========================================
    // Back to Top Button
    // ========================================
    const backToTop = document.getElementById('backToTop');

    if (backToTop) {
        window.addEventListener('scroll', function () {
            if (window.pageYOffset > 300) {
                backToTop.classList.add('show');
            } else {
                backToTop.classList.remove('show');
            }
        });

        backToTop.addEventListener('click', function () {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    // ========================================
    // Console Welcome Message
    // ========================================
    console.log('%c🚀 RACH INFRA GearOnRent - Batching Plant Rental',
        'background: linear-gradient(135deg, #FF6B35, #1E3A8A); color: white; padding: 10px 20px; font-size: 16px; border-radius: 5px;'
    );

});
