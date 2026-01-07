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
    const areaWrapper = document.getElementById('areaWrapper');
    const designMixSection = document.getElementById('stepDesignMix');
    const civilScope = document.getElementById('gear_civil_scope');
    const civilChecklist = document.getElementById('civilCostChecklist');
    const mgqField = document.getElementById('mgq_monthly');
    const totalProjectQtyField = document.getElementById('total_project_qty');
    const durationMonthsField = document.getElementById('project_duration_months');
    const durationYearsField = document.getElementById('gear_project_duration_years');
    const durationYearsPlaceholder = durationYearsField
        ? durationYearsField.querySelector('option[value=""]')
        : false;
    const applyMgqSuggestionBtn = document.getElementById('applyMgqSuggestion');
    const mgqSuggestionText = document.getElementById('mgqSuggestionText');
    const successMessage = document.getElementById('successMessage');
    const quoteNumber = document.getElementById('quoteNumber');
    const quoteDownload = document.getElementById('quoteDownload');
    const newQuoteRequest = document.getElementById('newQuoteRequest');
    const quotePreview = document.getElementById('quotePreview');
    const quotePreviewFrame = document.getElementById('quotePreviewFrame');
    const partnerNameField = document.getElementById('partner_name');
    const companyNameField = document.getElementById('company_name');
    const emailField = document.getElementById('email');
    const phoneField = document.getElementById('phone');
    const capacityField = document.getElementById('gear_capacity_id');
    const materialAreaField = document.getElementById('gear_material_area_id');
    const expectedProductionField = document.getElementById('gear_expected_production_qty');
    const designMixField = document.getElementById('gear_design_mix_ids');
    const noteField = document.getElementById('note');
    const serviceTypeGrid = document.getElementById('serviceTypeGrid');
    const formErrorBanner = document.getElementById('formErrorBanner');
    const pricingModal = document.getElementById('pricingTypeModal');
    const pricingTypeInput = document.getElementById('pricingTypeInput');
    const pricingOptions = pricingModal ? pricingModal.querySelectorAll('.pricing-option') : [];
    const pricingContinueBtn = document.getElementById('pricingTypeContinue');
    const pricingCloseBtn = document.getElementById('pricingTypeClose');
    const pricingCancelBtn = document.getElementById('pricingTypeCancel');
    const previewService = document.getElementById('previewService');
    const previewInventory = document.getElementById('previewInventory');
    const previewCapacity = document.getElementById('previewCapacity');
    const previewMgq = document.getElementById('previewMgq');
    const previewDuration = document.getElementById('previewDuration');
    const previewArea = document.getElementById('previewArea');
    const previewDesignMix = document.getElementById('previewDesignMix');
    const previewOptional = document.getElementById('previewOptional');
    const previewEstimateValue = document.getElementById('previewEstimateValue');
    const previewEstimateNote = document.getElementById('previewEstimateNote');
    const previewContactName = document.getElementById('previewContactName');
    const previewCompany = document.getElementById('previewCompany');
    const previewContactEmail = document.getElementById('previewContactEmail');
    const previewContactPhone = document.getElementById('previewContactPhone');
    const serviceTypeInputs = document.querySelectorAll('input[name="gear_service_type"]');
    const advancedCard = document.getElementById('advancedCard');
    const advancedToggle = document.getElementById('advancedToggle');
    const advancedSection = document.getElementById('advancedSection');
    const advancedScrollUp = document.getElementById('advancedScrollUp');
    const advancedScrollDown = document.getElementById('advancedScrollDown');
    const advancedScrollEnd = document.getElementById('advancedScrollEnd');
    const floatingInputs = document.querySelectorAll('.floating-label input, .floating-label select, .floating-label textarea');
    const rippleTargets = document.querySelectorAll('.ripple-effect');
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    let mgqManuallyEdited = false;
    let isSyncingLinkedQty = false;
    let estimateAbortController = null;
    let scheduleEstimatePreview = () => {};

    const debounce = (fn, wait = 400) => {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), wait);
        };
    };

    const refreshAdvancedHeight = () => {
        if (!(advancedCard && advancedSection && advancedCard.classList.contains('expanded'))) {
            return;
        }
        requestAnimationFrame(() => {
            advancedSection.style.maxHeight = `${advancedSection.scrollHeight}px`;
        });
    };

    const formatAutoQuantity = (value) => {
        if (value === '' || value === null || typeof value === 'undefined') {
            return '';
        }
        const numeric = typeof value === 'number' ? value : parseFloat(value);
        return Number.isFinite(numeric) ? numeric.toFixed(2) : '';
    };

    const setLinkedQuantityValue = (value, options = {}) => {
        const { source, manual = false } = options;
        if (isSyncingLinkedQty) {
            return;
        }
        isSyncingLinkedQty = true;
        const finalValue = manual ? (value ?? '') : formatAutoQuantity(value);
        if (totalProjectQtyField && source !== 'total') {
            totalProjectQtyField.value = finalValue;
            setFloatingLabelState(totalProjectQtyField);
        }
        if (expectedProductionField && source !== 'expected') {
            expectedProductionField.value = finalValue;
            setFloatingLabelState(expectedProductionField);
        }
        isSyncingLinkedQty = false;
        refreshAdvancedHeight();
    };

    const setAdvancedExpanded = (forceState) => {
        if (!(advancedCard && advancedSection)) {
            return;
        }
        const shouldExpand = typeof forceState === 'boolean'
            ? forceState
            : !advancedCard.classList.contains('expanded');
        advancedCard.classList.toggle('expanded', shouldExpand);
        if (advancedToggle) {
            advancedToggle.setAttribute('aria-expanded', shouldExpand ? 'true' : 'false');
        }
        advancedSection.setAttribute('aria-hidden', shouldExpand ? 'false' : 'true');
        if (shouldExpand) {
            advancedSection.style.maxHeight = `${advancedSection.scrollHeight}px`;
        } else {
            advancedSection.style.maxHeight = '';
        }
    };
    const scrollToElementWithOffset = (element) => {
        if (!element) {
            return;
        }
        const top = element.getBoundingClientRect().top + window.pageYOffset - 100;
        window.scrollTo({ top, behavior: 'smooth' });
    };
    const durationYearValues = durationYearsField
        ? Array.from(durationYearsField.options)
            .map(option => option.value)
            .filter(Boolean)
        : [];
    const setFloatingLabelState = (element) => {
        if (!element) {
            return;
        }
        const wrapper = element.closest('.floating-label');
        if (!wrapper) {
            return;
        }
        if (element.value && element.value.toString().trim() !== '') {
            wrapper.classList.add('has-value');
        } else {
            wrapper.classList.remove('has-value');
        }
    };

    const clearFormErrorBanner = () => {
        if (formErrorBanner) {
            formErrorBanner.classList.remove('visible');
            formErrorBanner.textContent = '';
        }
    };

    const showFormErrorBanner = (message) => {
        if (formErrorBanner) {
            formErrorBanner.textContent = message;
            formErrorBanner.classList.add('visible');
        } else {
            alert(message);
        }
    };

    const clearFieldErrorState = (element) => {
        if (!element) {
            return;
        }
        const wrapper = element.closest('.floating-label');
        if (wrapper && wrapper.classList.contains('has-error')) {
            wrapper.classList.remove('has-error');
            const errorText = wrapper.querySelector('.form-error-text');
            if (errorText) {
                errorText.remove();
            }
        }
        if (!document.querySelector('.floating-label.has-error') && !(serviceTypeGrid && serviceTypeGrid.classList.contains('has-error'))) {
            clearFormErrorBanner();
        }
    };

    const showFieldError = (element, message) => {
        if (!element) {
            return;
        }
        const wrapper = element.closest('.floating-label');
        if (!wrapper) {
            return;
        }
        wrapper.classList.add('has-error');
        let errorText = wrapper.querySelector('.form-error-text');
        if (!errorText) {
            errorText = document.createElement('small');
            errorText.className = 'form-error-text';
            wrapper.appendChild(errorText);
        }
        errorText.textContent = message;
    };

    const showGroupError = (container, message) => {
        if (!container) {
            return;
        }
        container.classList.add('has-error');
        let hint = container.nextElementSibling;
        if (!hint || !hint.classList.contains('form-error-text')) {
            hint = document.createElement('small');
            hint.className = 'form-error-text';
            container.parentNode.insertBefore(hint, container.nextSibling);
        }
        hint.textContent = message;
    };

    const clearGroupError = (container) => {
        if (!container) {
            return;
        }
        container.classList.remove('has-error');
        const hint = container.nextElementSibling;
        if (hint && hint.classList.contains('form-error-text')) {
            hint.remove();
        }
        if (!document.querySelector('.floating-label.has-error') && !container.classList.contains('has-error')) {
            clearFormErrorBanner();
        }
    };

    const clearInlineErrors = () => {
        document.querySelectorAll('.form-error-text').forEach(err => err.remove());
        document.querySelectorAll('.floating-label.has-error').forEach(wrapper => wrapper.classList.remove('has-error'));
        if (serviceTypeGrid) {
            serviceTypeGrid.classList.remove('has-error');
        }
        clearFormErrorBanner();
    };

    const resetEstimatePreview = () => {
        if (estimateAbortController) {
            estimateAbortController.abort();
            estimateAbortController = null;
        }
        if (previewEstimateValue) {
            previewEstimateValue.textContent = '—';
        }
        if (previewEstimateNote) {
            previewEstimateNote.textContent = 'Costs are shared once your quote is generated';
        }
    };

    const applyEstimatePreview = (rateSummary) => {
        if (!(previewEstimateValue && previewEstimateNote)) {
            return;
        }
        if (!rateSummary || (!rateSummary.per_cum_display && !rateSummary.monthly_display)) {
            resetEstimatePreview();
            return;
        }
        const headline = rateSummary.monthly_display || rateSummary.per_cum_display || '—';
        previewEstimateValue.textContent = headline;
        const parts = [];
        if (rateSummary.per_cum_display) {
            parts.push(`${rateSummary.per_cum_display} per CUM`);
        }
        if (rateSummary.mgq) {
            const mgqText = Number.isFinite(rateSummary.mgq) ? rateSummary.mgq.toFixed(2) : rateSummary.mgq;
            parts.push(`MGQ ${mgqText}`);
        }
        previewEstimateNote.textContent = parts.length ? parts.join(' • ') : 'Quoted rate available in PDF';
    };

    const refreshFloatingLabels = () => {
        floatingInputs.forEach(field => setFloatingLabelState(field));
    };

    floatingInputs.forEach(field => {
        setFloatingLabelState(field);
        ['input', 'change'].forEach(evt => {
            field.addEventListener(evt, () => {
                clearFieldErrorState(field);
                setFloatingLabelState(field);
                updatePreview();
            });
        });
    });

    const setDurationPlaceholder = (text) => {
        if (durationYearsPlaceholder) {
            durationYearsPlaceholder.textContent = text && text.trim() ? text : 'Select duration';
        }
    };

    const syncDurationYearsFromMonths = () => {
        if (!(durationYearsField && durationMonthsField)) {
            return;
        }
        const months = parseFloat(durationMonthsField.value || 0);
        if (!months) {
            durationYearsField.value = '';
            setDurationPlaceholder('Select duration');
            setFloatingLabelState(durationYearsField);
            return;
        }
        const matchedYear = durationYearValues.find(yearValue => {
            const yearFloat = parseFloat(yearValue);
            return yearFloat && Math.abs(months - yearFloat * 12) < 0.01;
        });
        durationYearsField.value = matchedYear || '';
        setFloatingLabelState(durationYearsField);
        if (matchedYear) {
            setDurationPlaceholder('Select duration');
        } else {
            const approxYears = months / 12;
            if (approxYears > 0) {
                setDurationPlaceholder(`Custom ~ ${approxYears.toFixed(2)} yrs`);
            } else {
                setDurationPlaceholder('Select duration');
            }
        }
    };

    const toggleInventorySections = () => {
        if (!inventoryMode) return;
        const isInventory = inventoryMode.value === 'with_inventory';

        document.querySelectorAll('.inventory-only').forEach(section => {
            section.classList.toggle('active', isInventory);
        });

        if (gradeWrapper) {
            gradeWrapper.style.display = isInventory ? 'block' : 'none';
            if (!isInventory) {
                const gradeSelect = gradeWrapper.querySelector('select');
                if (gradeSelect) gradeSelect.value = '';
            }
        }
        if (areaWrapper) {
            areaWrapper.style.display = isInventory ? 'grid' : 'none';
            if (!isInventory) {
                const areaSelect = areaWrapper.querySelector('select');
                if (areaSelect) areaSelect.value = '';
                const expectedInput = areaWrapper.querySelector('input[name="gear_expected_production_qty"]');
                if (expectedInput) expectedInput.value = '';
            }
        }
        if (designMixSection) {
            designMixSection.style.display = isInventory ? 'block' : 'none';
        }
        refreshFloatingLabels();
    };

    const toggleCivilChecklist = () => {
        if (!civilScope || !civilChecklist) return;
        const show = civilScope.value === 'vendor';
        civilChecklist.style.display = show ? 'flex' : 'none';
    };

    const computeDurationMonths = () => {
        const durationMonths = parseFloat(durationMonthsField ? durationMonthsField.value : '') || 0;
        if (durationMonths) return durationMonths;
        const years = parseFloat(durationYearsField ? durationYearsField.value : '') || 0;
        return years ? years * 12 : 0;
    };

    const computeDurationMonthsOrOne = () => {
        const months = computeDurationMonths();
        return months || 1;
    };

    const computeSuggestedMgq = () => {
        const totalQty = parseFloat(totalProjectQtyField ? totalProjectQtyField.value : '') || 0;
        const months = computeDurationMonths();
        if (totalQty > 0 && months > 0) {
            const suggested = totalQty / months;
            if (!mgqManuallyEdited || !(mgqField && mgqField.value)) {
                if (mgqField) {
                    mgqField.value = suggested.toFixed(2);
                    setFloatingLabelState(mgqField);
                }
                mgqManuallyEdited = false;
                updatePreview();
            }
            if (mgqSuggestionText) {
                mgqSuggestionText.textContent = mgqManuallyEdited
                    ? 'Updated MGQ applied.'
                    : `Suggested MGQ: ${suggested.toFixed(2)} m³/month`;
            }
            return suggested;
        }
        if (mgqSuggestionText) {
            mgqSuggestionText.textContent = mgqManuallyEdited ? 'Updated MGQ applied.' : 'Enter values to see suggested MGQ.';
        }
        return false;
    };

    function updateMgqSuggestion() {
        return computeSuggestedMgq();
    }
    if (typeof window !== 'undefined') {
        window.updateMgqSuggestion = updateMgqSuggestion;
    }

    function updateProjectQtyFromMgq() {
        if (!mgqField || (!totalProjectQtyField && !expectedProductionField)) {
            return;
        }
        const mgq = parseFloat(mgqField.value || '');
        const months = computeDurationMonths();
        if (mgq && months) {
            setLinkedQuantityValue(mgq * months);
        } else if (!mgq || !months) {
            setLinkedQuantityValue('', { manual: true });
        }
    }
    if (typeof window !== 'undefined') {
        window.updateProjectQtyFromMgq = updateProjectQtyFromMgq;
    }

    const setSuggestedMgq = () => {
        mgqManuallyEdited = false;
        const suggested = updateMgqSuggestion();
        if (suggested && mgqField) {
            mgqField.value = suggested.toFixed(2);
            setFloatingLabelState(mgqField);
            if (mgqSuggestionText) {
                mgqSuggestionText.textContent = `Suggested MGQ: ${suggested.toFixed(2)} m³/month`;
            }
            updateProjectQtyFromMgq();
            updatePreview();
        }
    };

    const getSelectedServiceTypeInput = () => document.querySelector('input[name="gear_service_type"]:checked');

    const getSelectedServiceTypeValue = () => {
        const selected = getSelectedServiceTypeInput();
        return selected ? selected.value : '';
    };

    const getSelectedServiceTypeLabel = () => {
        const selected = getSelectedServiceTypeInput();
        return selected ? (selected.dataset.label || selected.value) : '';
    };

    const collectOptionalServices = () => {
        const services = [];
        document.querySelectorAll('.js-optional-rate-input').forEach(input => {
            const flagField = input.dataset.flagField;
            const labelText = input.closest('.optional-service-card')?.querySelector('.optional-service-name')?.textContent?.trim();
            const checkbox = flagField ? document.querySelector(`input[name='${flagField}']`) : null;
            if (checkbox && checkbox.checked && input.value) {
                services.push(`${labelText || 'Optional'} x ${input.value}`);
            }
        });
        return services;
    };

    const updatePreview = () => {
        if (!(previewService && previewInventory && previewCapacity && previewMgq && previewDuration && previewArea && previewDesignMix && previewOptional)) return;
        const capacitySelect = document.getElementById('gear_capacity_id');
        const areaSelect = document.getElementById('gear_material_area_id');
        const designSelect = document.getElementById('gear_design_mix_ids');
        const nameValue = partnerNameField && partnerNameField.value ? partnerNameField.value.trim() : '';
        const companyValue = companyNameField && companyNameField.value ? companyNameField.value.trim() : '';
        const emailValue = emailField && emailField.value ? emailField.value.trim() : '';
        const phoneValue = phoneField && phoneField.value ? phoneField.value.trim() : '';

        const toggleSectionVisibility = (sectionClass, shouldShow) => {
            document.querySelectorAll(sectionClass).forEach(section => {
                section.classList.toggle('has-values', shouldShow);
            });
        };

        toggleSectionVisibility('.contact-panel', Boolean(nameValue || companyValue || emailValue || phoneValue));

        if (previewContactName) {
            previewContactName.textContent = nameValue;
            previewContactName.closest('li')?.classList.toggle('has-value', Boolean(nameValue));
        }
        if (previewCompany) {
            previewCompany.textContent = companyValue;
            previewCompany.closest('li')?.classList.toggle('has-value', Boolean(companyValue));
        }
        if (previewContactEmail) {
            previewContactEmail.textContent = emailValue;
            previewContactEmail.closest('li')?.classList.toggle('has-value', Boolean(emailValue));
        }
        if (previewContactPhone) {
            previewContactPhone.textContent = phoneValue;
            previewContactPhone.closest('li')?.classList.toggle('has-value', Boolean(phoneValue));
        }

        const serviceLabel = getSelectedServiceTypeLabel();
        const inventoryText = inventoryMode && inventoryMode.selectedOptions[0]?.textContent || '';
        const capacityText = capacitySelect && capacitySelect.selectedOptions[0]?.textContent || '';
        previewService.textContent = serviceLabel || '';
        previewService.parentElement?.classList.toggle('has-value', Boolean(serviceLabel));
        previewInventory.textContent = inventoryText;
        previewInventory.parentElement?.classList.toggle('has-value', Boolean(inventoryText));
        previewCapacity.textContent = capacityText;
        previewCapacity.parentElement?.classList.toggle('has-value', Boolean(capacityText));
        const mgqValue = mgqField && mgqField.value ? `${mgqField.value} m³` : '';
        previewMgq.textContent = mgqValue;
        previewMgq.closest('.metric-card')?.classList.toggle('has-value', Boolean(mgqValue));

        const years = durationYearsField && durationYearsField.selectedOptions[0]?.textContent;
        const months = durationMonthsField && durationMonthsField.value ? `${durationMonthsField.value} months` : '';
        const durationValue = months || years || '';
        previewDuration.textContent = durationValue;
        previewDuration.closest('.metric-card')?.classList.toggle('has-value', Boolean(durationValue));

        const areaValue = areaSelect && areaSelect.selectedOptions[0]?.textContent || '';
        previewArea.textContent = areaValue;
        previewArea.closest('.metric-card')?.classList.toggle('has-value', Boolean(areaValue));
        if (designSelect) {
            const selectedDesigns = Array.from(designSelect.selectedOptions).map(option => option.textContent);
            previewDesignMix.textContent = selectedDesigns.length ? selectedDesigns.join(', ') : '';
            previewDesignMix.parentElement?.classList.toggle('has-value', Boolean(selectedDesigns.length));
        } else {
            previewDesignMix.textContent = '';
        }

        const optionalList = collectOptionalServices();
        previewOptional.textContent = optionalList.length ? optionalList.join(', ') : '';
        previewOptional.parentElement?.classList.toggle('has-value', Boolean(optionalList.length));
        toggleSectionVisibility('.requirements-panel', Boolean(mgqValue || durationValue || areaValue || capacityText));
        toggleSectionVisibility('.service-panel', Boolean(serviceLabel || inventoryText || (designSelect && designSelect.value) || optionalList.length));
        toggleSectionVisibility('.estimate-panel', Boolean(mgqValue && capacityText && durationValue));
        scheduleEstimatePreview();
    };

    if (inventoryMode) {
        inventoryMode.addEventListener('change', () => {
            toggleInventorySections();
            updatePreview();
        });
        toggleInventorySections();
    }

    if (civilScope) {
        civilScope.addEventListener('change', toggleCivilChecklist);
        toggleCivilChecklist();
    }

    if (durationYearsField && durationMonthsField) {
        durationYearsField.addEventListener('change', () => {
            if (durationYearsField.value) {
                durationMonthsField.value = parseFloat(durationYearsField.value) * 12;
                setFloatingLabelState(durationMonthsField);
            } else if (durationMonthsField) {
                durationMonthsField.value = '';
                setFloatingLabelState(durationMonthsField);
            }
            syncDurationYearsFromMonths();
            setDurationPlaceholder('Select duration');
            setFloatingLabelState(durationYearsField);
            updateMgqSuggestion();
            updateProjectQtyFromMgq();
            updatePreview();
        });
        durationMonthsField.addEventListener('input', () => {
            syncDurationYearsFromMonths();
            updateMgqSuggestion();
            updateProjectQtyFromMgq();
            updatePreview();
        });
    }

    if (mgqField) {
        mgqField.addEventListener('input', () => {
            if (mgqField.value && mgqField.value.toString().trim() !== '') {
                mgqManuallyEdited = true;
                if (mgqSuggestionText) {
                    mgqSuggestionText.textContent = 'Updated MGQ applied.';
                }
            } else {
                mgqManuallyEdited = false;
                if (mgqSuggestionText) {
                    mgqSuggestionText.textContent = 'Enter values to see suggested MGQ.';
                }
            }
            updateProjectQtyFromMgq();
            updatePreview();
        });
    }

    const handleManualQuantityInput = (source) => {
        mgqManuallyEdited = false;
        const value = source === 'total'
            ? (totalProjectQtyField ? totalProjectQtyField.value : '')
            : (expectedProductionField ? expectedProductionField.value : '');
        setLinkedQuantityValue(value, { source, manual: true });
        updateMgqSuggestion();
        updatePreview();
    };

    if (totalProjectQtyField) {
        ['input', 'change'].forEach(evt => {
            totalProjectQtyField.addEventListener(evt, () => handleManualQuantityInput('total'));
        });
    }

    if (expectedProductionField) {
        ['input', 'change'].forEach(evt => {
            expectedProductionField.addEventListener(evt, () => handleManualQuantityInput('expected'));
        });
    }

    if (applyMgqSuggestionBtn) {
        applyMgqSuggestionBtn.addEventListener('click', setSuggestedMgq);
    }

    ['gear_capacity_id', 'gear_material_area_id', 'gear_design_mix_ids', 'gear_project_duration_years', 'gear_civil_scope'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', updatePreview);
        }
    });

    const syncServiceCards = () => {
        serviceTypeInputs.forEach(input => {
            const card = input.closest('.radio-card');
            if (card) {
                card.classList.toggle('selected', input.checked);
            }
        });
    };

    if (serviceTypeInputs.length) {
        serviceTypeInputs.forEach(input => {
            input.addEventListener('change', () => {
                syncServiceCards();
                clearGroupError(serviceTypeGrid);
                updatePreview();
            });
        });
        syncServiceCards();
    }

    const optionalToggles = document.querySelectorAll('.js-optional-service-toggle');
    optionalToggles.forEach(toggle => {
        const wrapper = toggle.closest('.optional-service-card');
        const qtyInput = wrapper ? wrapper.querySelector('.js-optional-rate-input') : null;
        const syncOptionalState = () => {
            if (!qtyInput) {
                return;
            }
            if (toggle.checked) {
                qtyInput.readOnly = false;
                if (!qtyInput.value) {
                    qtyInput.value = 1;
                }
            } else {
                qtyInput.readOnly = true;
                qtyInput.value = '';
            }
        };
        toggle.addEventListener('change', syncOptionalState);
        syncOptionalState();
    });

    document.querySelectorAll('.optional-service-card input, #gear_expected_production_qty').forEach(el => {
        el.addEventListener('input', updatePreview);
        el.addEventListener('change', updatePreview);
    });

    if (advancedCard && advancedToggle && advancedSection) {
        const initExpanded = advancedCard.classList.contains('expanded');
        advancedToggle.setAttribute('role', 'button');
        advancedToggle.setAttribute('tabindex', '0');
        advancedToggle.setAttribute('aria-expanded', initExpanded ? 'true' : 'false');
        advancedSection.setAttribute('aria-hidden', initExpanded ? 'false' : 'true');
        if (initExpanded) {
            advancedSection.style.maxHeight = `${advancedSection.scrollHeight}px`;
        }

        const handleAdvancedToggle = () => setAdvancedExpanded();
        advancedToggle.addEventListener('click', (event) => {
            event.preventDefault();
            handleAdvancedToggle();
        });
        advancedToggle.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') {
                event.preventDefault();
                handleAdvancedToggle();
            }
        });
    }

    const ensureAdvancedAndScroll = (target) => {
        setAdvancedExpanded(true);
        scrollToElementWithOffset(target);
    };

    if (advancedScrollUp) {
        advancedScrollUp.addEventListener('click', (e) => {
            e.preventDefault();
            ensureAdvancedAndScroll(advancedCard || advancedToggle || advancedSection);
        });
    }

    if (advancedScrollDown) {
        advancedScrollDown.addEventListener('click', (e) => {
            e.preventDefault();
            const target = advancedScrollEnd || (advancedSection ? advancedSection.lastElementChild : null) || advancedSection;
            ensureAdvancedAndScroll(target);
        });
    }

    if (advancedCard && advancedSection) {
        window.addEventListener('resize', refreshAdvancedHeight);
    }

    rippleTargets.forEach(target => {
        target.addEventListener('click', (event) => {
            const rect = target.getBoundingClientRect();
            const ripple = document.createElement('span');
            ripple.className = 'ripple';
            ripple.style.left = `${event.clientX - rect.left}px`;
            ripple.style.top = `${event.clientY - rect.top}px`;
            target.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    });

    resetEstimatePreview();
    syncDurationYearsFromMonths();
    updateMgqSuggestion();
    updateProjectQtyFromMgq();
    updatePreview();

    const clearPricingSelection = () => {
        if (pricingOptions) {
            pricingOptions.forEach(option => option.classList.remove('selected'));
        }
        if (pricingTypeInput) {
            pricingTypeInput.value = '';
        }
        if (pricingContinueBtn) {
            pricingContinueBtn.disabled = true;
        }
    };

    const closePricingModal = () => {
        if (pricingModal) {
            pricingModal.classList.remove('show');
            pricingModal.setAttribute('aria-hidden', 'true');
        }
    };

    const openPricingModal = () => {
        if (pricingModal) {
            pricingModal.classList.add('show');
            pricingModal.setAttribute('aria-hidden', 'false');
        }
    };

    if (pricingOptions && pricingContinueBtn) {
        const ensureDefaultPricing = () => {
            if (!pricingTypeInput || pricingTypeInput.value) {
                return;
            }
            const firstOption = pricingOptions[0];
            if (firstOption) {
                pricingOptions.forEach(btn => btn.classList.remove('selected'));
                firstOption.classList.add('selected');
                pricingTypeInput.value = firstOption.dataset.pricingType || '';
                pricingContinueBtn.disabled = !pricingTypeInput.value;
                updatePreview();
            }
        };

        pricingOptions.forEach(option => {
            option.addEventListener('click', () => {
                pricingOptions.forEach(btn => btn.classList.remove('selected'));
                option.classList.add('selected');
                if (pricingTypeInput) {
                    pricingTypeInput.value = option.dataset.pricingType || '';
                }
                pricingContinueBtn.disabled = !option.dataset.pricingType;
                updatePreview();
            });
        });

        ensureDefaultPricing();
    }

    [pricingCloseBtn, pricingCancelBtn].forEach(btn => {
        if (btn) {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                clearPricingSelection();
                closePricingModal();
            });
        }
    });

    if (pricingModal) {
        pricingModal.addEventListener('click', (e) => {
            if (e.target === pricingModal) {
                clearPricingSelection();
                closePricingModal();
            }
        });
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
        resetEstimatePreview();
        clearPricingSelection();
        closePricingModal();
    };

    if (newQuoteRequest && contactForm) {
        newQuoteRequest.addEventListener('click', () => {
            contactForm.reset();
            clearInlineErrors();
            refreshFloatingLabels();
            toggleInventorySections();
            toggleCivilChecklist();
            setDurationPlaceholder('Select duration');
            syncDurationYearsFromMonths();
            resetSuccessState();
            closePricingModal();
            clearPricingSelection();
            formSuccess.classList.remove('show');
            contactForm.style.display = 'block';
            contactForm.scrollIntoView({ behavior: 'smooth' });
        });
    }

    const collectOptionalAmounts = () => {
        const amounts = {};
        document.querySelectorAll('.js-optional-rate-input').forEach(input => {
            const fieldName = input.getAttribute('name');
            const flagField = input.dataset.flagField;
            const checkbox = flagField ? document.querySelector(`input[name='${flagField}']`) : null;
            const isEnabled = checkbox ? checkbox.checked : false;
            const qty = parseFloat(input.value || 0);
            const rate = parseFloat(input.dataset.rate || 0);
            amounts[fieldName] = isEnabled ? qty * rate : 0;
        });
        return amounts;
    };

    const collectFormData = () => {
        const designSelect = designMixField;
        const selectedDesignMixes = designSelect
            ? Array.from(designSelect.selectedOptions).map(option => option.value).filter(Boolean)
            : [];

        const optionalAmounts = collectOptionalAmounts();
        const isChecked = (name) => {
            const field = document.querySelector(`input[name='${name}']`);
            return field ? field.checked : false;
        };

        return {
            partner_name: partnerNameField ? partnerNameField.value.trim() : '',
            company_name: companyNameField ? companyNameField.value.trim() : '',
            email: emailField ? emailField.value.trim() : '',
            phone: phoneField ? phoneField.value.trim() : '',
            gear_service_type: getSelectedServiceTypeValue(),
            gear_capacity_id: capacityField ? capacityField.value : '',
            mgq_monthly: mgqField ? mgqField.value : '',
            project_quantity: totalProjectQtyField ? totalProjectQtyField.value : '',
            gear_expected_production_qty: expectedProductionField ? expectedProductionField.value : '',
            x_inventory_mode: inventoryMode ? inventoryMode.value : '',
            gear_design_mix_id: selectedDesignMixes[0] || '',
            gear_design_mix_ids: selectedDesignMixes,
            gear_material_area_id: materialAreaField ? materialAreaField.value : '',
            gear_project_duration_years: durationYearsField ? durationYearsField.value : '',
            project_duration_years: durationYearsField ? durationYearsField.value : '',
            gear_project_duration_months: durationMonthsField ? durationMonthsField.value : '',
            gear_civil_scope: civilScope ? civilScope.value : '',
            note: noteField ? noteField.value : '',
            gear_transport_opt_in: isChecked('gear_transport_opt_in'),
            gear_transport_per_cum: optionalAmounts.gear_transport_per_cum || 0,
            gear_pumping_opt_in: isChecked('gear_pumping_opt_in'),
            gear_pump_per_cum: optionalAmounts.gear_pump_per_cum || 0,
            gear_manpower_opt_in: isChecked('gear_manpower_opt_in'),
            gear_manpower_per_cum: optionalAmounts.gear_manpower_per_cum || 0,
            gear_diesel_opt_in: isChecked('gear_diesel_opt_in'),
            gear_diesel_per_cum: optionalAmounts.gear_diesel_per_cum || 0,
            gear_jcb_opt_in: isChecked('gear_jcb_opt_in'),
            gear_jcb_monthly: optionalAmounts.gear_jcb_monthly || 0,
            pricing_type: pricingTypeInput ? pricingTypeInput.value : '',
        };
    };

    const canPreviewEstimate = (formData) => {
        if (!formData) {
            return false;
        }
        const hasDuration = (formData.gear_project_duration_years && formData.gear_project_duration_years.toString().trim() !== '')
            || (formData.gear_project_duration_months && formData.gear_project_duration_months.toString().trim() !== '');
        const emailValid = formData.email && emailRegex.test(formData.email);
        return Boolean(
            formData.partner_name
            && formData.email
            && emailValid
            && formData.phone
            && formData.mgq_monthly
            && formData.gear_capacity_id
            && formData.gear_service_type
            && formData.x_inventory_mode
            && hasDuration
            && formData.pricing_type
        );
    };

    const requestEstimatePreview = () => {
        const formData = collectFormData();
        if (!canPreviewEstimate(formData)) {
            resetEstimatePreview();
            return;
        }

        if (estimateAbortController) {
            estimateAbortController.abort();
        }
        estimateAbortController = new AbortController();

        fetch('/batching-plant/submit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: {
                    ...formData,
                    preview_only: true,
                },
                id: Date.now(),
            }),
            signal: estimateAbortController.signal,
        })
            .then(response => response.json())
            .then(data => {
                const result = data && data.result;
                if (result && result.success) {
                    applyEstimatePreview(result.rate_summary);
                } else {
                    resetEstimatePreview();
                }
            })
            .catch((error) => {
                if (error && error.name === 'AbortError') {
                    return;
                }
                resetEstimatePreview();
            })
            .finally(() => {
                estimateAbortController = null;
            });
    };

    scheduleEstimatePreview = debounce(requestEstimatePreview, 500);

    const validateForm = (formData) => {
        let isValid = true;
        clearInlineErrors();

        const requireField = (field, message) => {
            if (!field) {
                return;
            }
            if (!field.value || !field.value.toString().trim()) {
                showFieldError(field, message);
                isValid = false;
            }
        };

        requireField(partnerNameField, 'Full name is required.');
        requireField(emailField, 'Email address is required.');
        requireField(phoneField, 'Phone number is required.');
        requireField(mgqField, 'MGQ Monthly is required.');
        requireField(capacityField, 'Select a plant capacity.');
        requireField(inventoryMode, 'Choose an inventory mode.');

        const hasDuration = (formData.gear_project_duration_years && formData.gear_project_duration_years.trim()) ||
            (formData.gear_project_duration_months && formData.gear_project_duration_months.trim());
        if (!hasDuration && durationYearsField) {
            showFieldError(durationYearsField, 'Provide project duration.');
            isValid = false;
        }

        if (emailField && emailField.value && !emailRegex.test(emailField.value.trim())) {
            showFieldError(emailField, 'Enter a valid email address.');
            isValid = false;
        }

        if (!getSelectedServiceTypeValue()) {
            showGroupError(serviceTypeGrid, 'Select a service model to continue.');
            isValid = false;
        } else {
            clearGroupError(serviceTypeGrid);
        }

        if (formData.x_inventory_mode === 'with_inventory' && (!formData.gear_design_mix_ids || !formData.gear_design_mix_ids.length)) {
            showFieldError(designMixField, 'Select at least one design mix for inventory mode.');
            isValid = false;
        }

        if (!isValid) {
            showFormErrorBanner('Please review the highlighted fields before continuing.');
        } else {
            clearFormErrorBanner();
        }

        return isValid;
    };

    const submitBatchingForm = (providedData, options = {}) => {
        const formData = providedData || collectFormData();
        const skipValidation = options.skipValidation || false;

        if (!skipValidation && !validateForm(formData)) {
            return;
        }

        if (!formData.pricing_type) {
            showFormErrorBanner('Please choose a pricing type to continue.');
            openPricingModal();
            return;
        }

        const submitBtn = contactForm.querySelector('.btn-submit');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
        submitBtn.disabled = true;
        closePricingModal();

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
                     clearInlineErrors();
                    refreshFloatingLabels();
                    toggleInventorySections();
                    toggleCivilChecklist();
                    setDurationPlaceholder('Select duration');
                    syncDurationYearsFromMonths();
                    updateMgqSuggestion();
                    updatePreview();

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
                    applyEstimatePreview(result.rate_summary);
                } else {
                    const rpcError = data && data.error;
                    const resultError = result && result.error;
                    const rpcErrorMessage = rpcError && (rpcError.data?.message || rpcError.message);
                    const errorMessage = resultError || rpcErrorMessage || 'An error occurred. Please try again.';
                    console.error('Error:', errorMessage, data);
                    alert(errorMessage);
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
    };

    if (contactForm) {
        contactForm.addEventListener('submit', function (e) {
            e.preventDefault();

            const formData = collectFormData();
            if (!validateForm(formData)) {
                return;
            }

            if (!pricingTypeInput || !pricingTypeInput.value) {
                openPricingModal();
                return;
            }

            submitBatchingForm(formData, { skipValidation: true });
        });

        if (pricingContinueBtn) {
            pricingContinueBtn.addEventListener('click', () => {
                if (!pricingTypeInput || !pricingTypeInput.value) {
                    pricingContinueBtn.disabled = true;
                    return;
                }
                const formData = collectFormData();
                if (!validateForm(formData)) {
                    return;
                }
                submitBatchingForm(formData, { skipValidation: true });
            });
        }
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
