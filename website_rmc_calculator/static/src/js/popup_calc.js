/** @odoo-module **/
(function() {
  'use strict';

  // Wait for DOM to be fully loaded before initializing
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      console.log('RMC Calculator: DOM loaded, initializing...');
      initializeCalculator();
    });
  } else {
    console.log('RMC Calculator: DOM already loaded, initializing...');
    initializeCalculator();
  }

  function initializeCalculator() {

  const MODAL_ID = 'rmc-calc-modal';
  const RESULT_ID = 'dim_result';
  const OPEN_BTN_ID = 'open_dim_popup';
  const RMC_FIELD_ID = 'rmc_volume';
  const TRUCK_CAP_M3 = 7;
  const PRICE_ENDPOINT = '/rmc_calculator/price_breakdown';
  const VARIANTS_ENDPOINT = '/rmc_calculator/variants';
  const LOCATION_SAVE_ENDPOINT = '/rmc/location/save';
  const LOCATION_REVERSE_ENDPOINT = '/rmc/location/reverse';
  const CITY_INPUT_ID = 'rmc_city';
  const ZIP_INPUT_ID = 'rmc_zip';
  const CITY_GPS_BUTTON_ID = 'rmc_city_gps';
  const CITY_COOKIE_KEY = 'ri_loc_city';
  const ZIP_COOKIE_KEY = 'ri_loc_zip';

  let cityInputRef = null;
  let zipInputRef = null;
  let locationListenerBound = false;

  function readCookie(name) {
    return (document.cookie || '')
      .split(';')
      .map(function (item) { return item.trim(); })
      .filter(function (item) { return item.indexOf(name + '=') === 0; })
      .map(function (item) { return decodeURIComponent(item.substring(name.length + 1)); })
      .shift() || '';
  }

  // helper: JSON-RPC call wrapper (returns a Promise resolving to result or rejecting error)
  function jsonRpcCall(url, params, id) {
    try {
      return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: params || {}, id: typeof id !== 'undefined' ? id : Date.now() })
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (resp) {
          if (resp && resp.error) {
            return Promise.reject(resp.error);
          }
          return resp && Object.prototype.hasOwnProperty.call(resp, 'result') ? resp.result : resp;
        });
    } catch (e) {
      return Promise.reject(e);
    }
  }

  function getCurrencySymbol(code) {
    if (!code) {
      return '₹';
    }
    if (code === 'INR') {
      return '₹';
    }
    if (code.length <= 3) {
      return code + ' ';
    }
    return code;
  }

  function updatePriceSummary(data, ctx, volumeHint) {
    var priceEl = document.getElementById('variant_price') || (ctx && ctx.querySelector('#variant_price'));
    var baseEl = document.getElementById('base_price') || (ctx && ctx.querySelector('#base_price'));
    var totalEl = document.getElementById('estimated_total') || (ctx && ctx.querySelector('#estimated_total'));
    var discountEl = document.getElementById('bulk_discount') || (ctx && ctx.querySelector('#bulk_discount'));
    var truckEl = document.getElementById('truck_count') || (ctx && ctx.querySelector('#truck_count'));

    if (!data || !data.success) {
      if (priceEl) priceEl.textContent = 'Unit price: —';
      if (baseEl) baseEl.textContent = '—';
      if (totalEl) totalEl.textContent = '₹0';
      if (discountEl) discountEl.textContent = '₹0';
      if (truckEl) truckEl.textContent = '0';
      return;
    }

    var currency = getCurrencySymbol(data.currency);
    var unit = parseFloat(data.price || data.unit_price || 0) || 0;
    var baseTotal = parseFloat(data.base_price || 0);
    if (!baseTotal && volumeHint) {
      baseTotal = unit * volumeHint;
    }
    var computedTotal = parseFloat(data.computed_price || 0);
    if (!computedTotal && volumeHint) {
      computedTotal = unit * volumeHint;
    }
    var discountValue = parseFloat(data.discount_value || 0) || 0;
    var trucks = parseInt(data.truck_count || 0, 10) || 0;

    if (priceEl) priceEl.textContent = 'Unit price: ' + currency + unit.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (baseEl) baseEl.textContent = currency + (baseTotal || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (totalEl) totalEl.textContent = currency + (computedTotal || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (discountEl) {
      var prefix = discountValue > 0 ? '-' : '';
      discountEl.textContent = prefix + currency + Math.abs(discountValue).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    if (truckEl) truckEl.textContent = trucks ? trucks.toString() : '0';
  }

  function getLocationOverrides() {
    const overrides = {};
    const cityValue = cityInputRef && cityInputRef.value ? cityInputRef.value.toString().trim() : '';
    const zipValue = zipInputRef && zipInputRef.value ? zipInputRef.value.toString().trim() : '';
    if (cityValue) {
      overrides.city_override = cityValue;
    }
    if (zipValue) {
      overrides.zip_override = zipValue;
    }
    return overrides;
  }

  function refreshPriceAfterLocation() {
    const calcBtnPage = document.getElementById('calculate_quote_btn');
    const gradeSel = document.getElementById('grade_select');
    const variantSel = document.getElementById('variant_select');
    const volumeFieldLocal = document.getElementById(RMC_FIELD_ID);
    const qty = volumeFieldLocal && volumeFieldLocal.value ? parseFloat(volumeFieldLocal.value) : 0;
    const hasData = gradeSel && gradeSel.value && qty && qty > 0;
    if (!hasData || !calcBtnPage || !calcBtnPage._rmcBound) {
      return;
    }
    // avoid alert when grade selected but variant required? reuse existing click handler
    calcBtnPage._rmcAutoTrigger = true;
    calcBtnPage.click();
  }

  function fetchGpsManually() {
    return new Promise(function (resolve, reject) {
      if (!navigator.geolocation) {
        return reject(new Error('GPS is not available on this device.'));
      }
      navigator.geolocation.getCurrentPosition(
        function (position) {
          var coords = position.coords || {};
          var params = new URLSearchParams({
            lat: coords.latitude,
            lon: coords.longitude,
          });
          fetch(LOCATION_REVERSE_ENDPOINT + '?' + params.toString())
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (data && !data.error) {
                resolve(data);
              } else {
                reject(new Error((data && data.error) || 'We could not determine your location.'));
              }
            })
            .catch(function (err) {
              reject(err instanceof Error ? err : new Error('We could not determine your location.'));
            });
        },
        function (err) {
          reject(err instanceof Error ? err : new Error('We could not determine your location.'));
        },
        {
          enableHighAccuracy: false,
          timeout: 7000,
          maximumAge: 60000,
        }
      );
    });
  }

  function syncLocation(method) {
    const city = cityInputRef && cityInputRef.value ? cityInputRef.value.trim() : '';
    const zip = zipInputRef && zipInputRef.value ? zipInputRef.value.trim() : '';
    if (!city && !zip) {
      return Promise.resolve();
    }
    const payload = {
      city: city,
      method: method || 'manual',
    };
    if (zip) {
      payload.zip = zip;
    }
    if (window.rmcLocationManager && window.rmcLocationManager._saveLocation) {
      return window.rmcLocationManager
        ._saveLocation(payload, {
          reloadOnReprice: false,
          showBanner: false,
          updateForm: false,
          sourceMethod: payload.method,
        })
        .catch(function () {
          /* ignore */
        });
    }
    return fetch(LOCATION_SAVE_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json(); })
      .catch(function () {
        /* ignore */
      });
  }

  function setupLocationBinding() {
    if (setupLocationBinding._bound) {
      return;
    }
    cityInputRef = document.getElementById(CITY_INPUT_ID);
    zipInputRef = document.getElementById(ZIP_INPUT_ID);
    const gpsBtn = document.getElementById(CITY_GPS_BUTTON_ID);

    if (cityInputRef && !cityInputRef.value) {
      var cookieCity = readCookie(CITY_COOKIE_KEY);
      if (cookieCity) {
        cityInputRef.value = cookieCity;
      }
    }
    if (zipInputRef && !zipInputRef.value) {
      var cookieZip = readCookie(ZIP_COOKIE_KEY);
      if (cookieZip) {
        zipInputRef.value = cookieZip;
      }
    }
    if (window.rmcLocationManager && window.rmcLocationManager.state) {
      if (cityInputRef && !cityInputRef.value && window.rmcLocationManager.state.city) {
        cityInputRef.value = window.rmcLocationManager.state.city;
      }
      if (zipInputRef && !zipInputRef.value && window.rmcLocationManager.state.zip) {
        zipInputRef.value = window.rmcLocationManager.state.zip;
      }
    }

    const syncAndRefresh = function (method) {
      return syncLocation(method).then(function () {
        refreshPriceAfterLocation();
      });
    };

    if (cityInputRef && !cityInputRef._rmcBound) {
      cityInputRef.addEventListener('change', function () {
        syncAndRefresh('manual');
      });
      cityInputRef._rmcBound = true;
    }

    if (zipInputRef && !zipInputRef._rmcBound) {
      zipInputRef.addEventListener('change', function () {
        syncAndRefresh('manual');
      });
      zipInputRef._rmcBound = true;
    }

    if (gpsBtn && !gpsBtn._rmcBound) {
      gpsBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        gpsBtn.disabled = true;

        var applyResponse = function (response) {
          if (!response) {
            return;
          }
          if (cityInputRef) {
            cityInputRef.value = response.city || '';
          }
          if (zipInputRef) {
            zipInputRef.value = response.zip || '';
          }
          refreshPriceAfterLocation();
        };

        var promise;
        if (window.rmcLocationManager && window.rmcLocationManager.detectWithGps) {
          promise = window.rmcLocationManager.detectWithGps({
            reloadOnReprice: false,
            showBanner: false,
            updateForm: false,
          }).then(function (response) {
            applyResponse(response);
            return response;
          });
        } else {
          promise = fetchGpsManually().then(function (response) {
            if (!response || response.error) {
              throw new Error((response && response.error) || 'We could not determine your location.');
            }
            if (cityInputRef) {
              cityInputRef.value = response.city || '';
            }
            if (zipInputRef) {
              zipInputRef.value = response.zip || '';
            }
            return syncAndRefresh('gps').then(function () {
              applyResponse(response);
              return response;
            });
          });
        }

        promise.catch(function (error) {
          var message = (error && error.message) || 'We could not determine your location.';
          alert(message);
        }).finally(function () {
          gpsBtn.disabled = false;
        });
      });
      gpsBtn._rmcBound = true;
    }

    if (!locationListenerBound) {
      window.addEventListener('rmc-location-updated', function (ev) {
        var detail = (ev && ev.detail) || {};
        if (cityInputRef && detail.city) {
          cityInputRef.value = detail.city;
        }
        if (zipInputRef && detail.zip) {
          zipInputRef.value = detail.zip;
        }
        refreshPriceAfterLocation();
      });
      locationListenerBound = true;
    }

    if (!setupLocationBinding._initialSyncDone && cityInputRef && cityInputRef.value) {
      setupLocationBinding._initialSyncDone = true;
      syncAndRefresh('manual');
    } else {
      refreshPriceAfterLocation();
    }

    setupLocationBinding._bound = true;
  }

  let cachedTemplates = [];

  function fetchTemplatesList(limit) {
    return jsonRpcCall(VARIANTS_ENDPOINT, { template_id: null, limit: limit || 50 }, Date.now())
      .then(function (data) {
        const templates = (data && data.templates) || [];
        cachedTemplates = templates;
        return templates;
      })
      .catch(function () {
        cachedTemplates = [];
        return [];
      });
  }

  function renderTemplateOptions(select, templates) {
    if (!select) {
      return;
    }
    const previous = select.value;
    const placeholder = select.getAttribute('data-placeholder')
      || (select.options && select.options[0] && select.options[0].text)
      || 'Select concrete grade';
    select.innerHTML = '';
    const placeholderOption = document.createElement('option');
    placeholderOption.value = '';
    placeholderOption.textContent = placeholder;
    select.appendChild(placeholderOption);
    (templates || []).forEach(function (tmpl) {
      const option = document.createElement('option');
      option.value = tmpl.id;
      option.textContent = tmpl.name;
      option.dataset.brand = tmpl.brand || '';
      option.dataset.gradeType = tmpl.grade_type || '';
      select.appendChild(option);
    });
    if (previous && select.querySelector('option[value="' + previous + '"]')) {
      select.value = previous;
    }
  }

  function ensureTemplateOptions(select) {
    if (select) {
      if (cachedTemplates.length) {
        renderTemplateOptions(select, cachedTemplates);
        return Promise.resolve(cachedTemplates);
      }
      return fetchTemplatesList().then(function (templates) {
        renderTemplateOptions(select, templates);
        return templates;
      });
    }
    if (cachedTemplates.length) {
      return Promise.resolve(cachedTemplates);
    }
    return fetchTemplatesList();
  }

  function refreshAllTemplateSelects() {
    const selects = document.querySelectorAll('#grade_select');
    return ensureTemplateOptions(null).then(function (templates) {
      (selects || []).forEach(function (sel) {
        renderTemplateOptions(sel, templates);
      });
      return templates;
    });
  }

  function createModal() {
    // If already created, return
    if (document.getElementById(MODAL_ID)) return;

    const modal = document.createElement('div');
    modal.id = MODAL_ID;
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.style.cssText = `
      position: fixed; inset: 0; display: flex; align-items: center; justify-content: center;
      background: rgba(0,0,0,0.5); z-index: 100000;
    `;

    const wrapper = document.createElement('div');
    wrapper.style.cssText = `
      background: #fff; border-radius: 8px; padding: 18px; width: 92%; max-width: 420px;
      box-shadow: 0 6px 22px rgba(0,0,0,0.35); font-family: sans-serif;
    `;

    wrapper.innerHTML = `
      <h3 style="margin:0 0 12px 0;">RMC Volume Calculator</h3>
      <div style="margin-bottom:8px; display:flex; gap:8px; align-items:flex-end;">
        <div style="flex:1;">
          <label style="display:block">Length: <input id="calc-length" type="number" step="0.01" min="0" style="width:100%;"></label>
        </div>
        <div style="width:120px;">
          <label style="display:block">Unit:
            <select id="calc-length-unit" style="width:100%;">
              <option value="m">meters</option>
              <option value="ft">feet</option>
            </select>
          </label>
        </div>
      </div>
      <div style="margin-bottom:8px; display:flex; gap:8px; align-items:flex-end;">
        <div style="flex:1;">
          <label style="display:block">Width: <input id="calc-width" type="number" step="0.01" min="0" style="width:100%;"></label>
        </div>
        <div style="width:120px;">
          <label style="display:block">Unit:
            <select id="calc-width-unit" style="width:100%;">
              <option value="m">meters</option>
              <option value="ft">feet</option>
            </select>
          </label>
        </div>
      </div>
      <div style="margin-bottom:8px; display:flex; gap:8px; align-items:flex-end;">
        <div style="flex:1;">
          <label style="display:block">Thickness: <input id="calc-thickness" type="number" step="0.1" min="0" style="width:100%;"></label>
        </div>
        <div style="width:120px;">
          <label style="display:block">Unit:
            <select id="calc-thickness-unit" style="width:100%;">
              <option value="mm">mm</option>
              <option value="in">inches</option>

            </select>
          </label>
        </div>
      </div>
      <!-- Grade/Variant selectors (appear in modal if page doesn't provide them externally) -->
      
      <div style="margin-bottom:12px;">
        <label><input id="calc-stairs" type="checkbox"> Stairs (add 10%)</label>
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;">
        <button id="calc-calculate" type="button">Calculate</button>
        <button id="calc-insert" type="button" disabled>Insert to Requirement</button>
        <button id="calc-close" type="button">Close</button>
      </div>
      <div id="${RESULT_ID}" style="font-weight:600; margin-top:6px;"></div>
    `;

    modal.appendChild(wrapper);
    document.body.appendChild(modal);

    // If modal contains grade/variant selects, wire them up and populate
    try {
      const gradeSelModal = document.getElementById('grade_select');
      if (gradeSelModal) {
        gradeSelModal.addEventListener('change', function () { populateVariants(this.value); });
        // If a page-level grade_select exists (same id), clone its options into the modal
        try {
          // collect all grade_select elements on page; modal will be last one
          var allGradeSelects = document.querySelectorAll('#grade_select');
          if (allGradeSelects && allGradeSelects.length > 1) {
            var pageGradeSel = allGradeSelects[0];
            var modalGradeSel = allGradeSelects[allGradeSelects.length - 1];
            if (pageGradeSel && modalGradeSel && pageGradeSel.options && pageGradeSel.options.length) {
              // clear placeholder then clone options
              modalGradeSel.innerHTML = '';
              for (var i = 0; i < pageGradeSel.options.length; i++) {
                var opt = pageGradeSel.options[i].cloneNode(true);
                modalGradeSel.appendChild(opt);
              }
              // set same selected value
              modalGradeSel.value = pageGradeSel.value || '';
              if (modalGradeSel.value) populateVariants(modalGradeSel.value);
            }
          } else {
            // fallback: if only modal exists, try to read page-level select by name
            var alt = document.querySelector('select[name="product_tmpl_id"], select[name="grade_select"]');
            if (alt && alt !== gradeSelModal && alt.options && alt.options.length) {
              gradeSelModal.innerHTML = '';
              for (var j = 0; j < alt.options.length; j++) gradeSelModal.appendChild(alt.options[j].cloneNode(true));
            }
          }
        } catch (e) { /* ignore cloning errors */ }
        // try to set initial template id from page-level grade_select if present
        var pageGrade = (document.querySelectorAll('#grade_select')[0] || {}).value || null;
        if (pageGrade) {
          gradeSelModal.value = pageGrade;
          populateVariants(pageGrade);
        }
      }
    } catch (e) { /* ignore */ }

    // Bind events and keep handlers for cleanup
    const calculateBtn = document.getElementById('calc-calculate');
    const insertBtn = document.getElementById('calc-insert');
    const closeBtn = document.getElementById('calc-close');

    function handleCalculate() {
  // read raw inputs (scope to modal wrapper to avoid ID conflicts with page)
  var ctx = wrapper || document;
  const rawLength = parseFloat((ctx.querySelector('#calc-length') || {}).value) || 0;
  const rawWidth = parseFloat((ctx.querySelector('#calc-width') || {}).value) || 0;
  const rawThickness = parseFloat((ctx.querySelector('#calc-thickness') || {}).value) || 0;
  const lengthUnit = ((ctx.querySelector('#calc-length-unit') || {}).value) || 'm';
  const widthUnit = ((ctx.querySelector('#calc-width-unit') || {}).value) || 'm';
  const thicknessUnit = ((ctx.querySelector('#calc-thickness-unit') || {}).value) || 'mm';
  const stairs = !!(ctx.querySelector('#calc-stairs') && ctx.querySelector('#calc-stairs').checked);
      // convert dimensions to meters
      function toMeters(val, unit){
        switch(unit){
          case 'ft': return val * 0.3048;
          case 'm': return val;
          default: return val; // fallback
        }
      }
      function thicknessToMeters(val, unit){
        switch(unit){
          case 'mm': return val / 1000; // mm -> m
          case 'cm': return val / 100;  // cm -> m
          case 'in': return (val * 25.4) / 1000; // inches -> mm -> m
          case 'm': return val; // already meters
          default: return val / 1000; // assume mm
        }
      }

      var length = toMeters(rawLength, lengthUnit);
      var width = toMeters(rawWidth, widthUnit);
      var thickness = thicknessToMeters(rawThickness, thicknessUnit);
  const gradeSel = wrapper.querySelector('#grade_select') || document.getElementById('grade_select');
  const tmplId = gradeSel ? gradeSel.value : null;
  const variantSel = wrapper.querySelector('#variant_select') || document.getElementById('variant_select');
  const productId = variantSel && variantSel.value ? variantSel.value : (tmplId ? null : null);

  let volume = length * width * thickness;
      if (stairs) volume *= 1.10;
      volume = Math.round(volume * 1000) / 1000; // 3 decimals
      const truckCount = Math.ceil((volume || 0) / TRUCK_CAP_M3);

      let html = `Volume: ${volume} m³<br>Trucks needed: ${truckCount}`;
      if (volume < 3) html += '<br><span style="color:red">Warning: Minimum order is 3 m³</span>';

  const res = wrapper.querySelector('#' + RESULT_ID) || document.getElementById(RESULT_ID);
  if (res) res.innerHTML = html;
  if (insertBtn) insertBtn.disabled = false;

  // Fetch price if we have either a variant or at least a template selected
  if (tmplId) {
    const payload = (variantSel && variantSel.value)
      ? { product_id: variantSel.value, qty: volume }
      : { product_tmpl_id: tmplId, qty: volume };
    Object.assign(payload, getLocationOverrides());
    jsonRpcCall(PRICE_ENDPOINT, payload, Date.now())
      .then(function (summary) {
        updatePriceSummary(summary, wrapper, volume);
      })
      .catch(function () {
        updatePriceSummary(null, wrapper);
      });
  }
    }

    // populate variants when template changes
  // NOTE: variant population listener moved outside createModal() so it runs on page load

    function handleInsert() {
      const res = document.getElementById(RESULT_ID);
      if (!res) return;
      const match = res.textContent.match(/Volume:\s*([\d.]+)\s*m³/);
      if (!match) return;
      const volume = match[1];
      const field = document.getElementById(RMC_FIELD_ID);
      if (field) {
        field.value = volume;
        field.dispatchEvent(new Event('change', { bubbles: true }));
      }
      destroyModal(); // cleanup after insert
    }

    function handleClose() {
      destroyModal(); // cleanup on close
    }

    // Attach listeners
    calculateBtn.addEventListener('click', handleCalculate);
    insertBtn.addEventListener('click', handleInsert);
    closeBtn.addEventListener('click', handleClose);

    // close modal by clicking backdrop (outside wrapper)
    modal.addEventListener('click', function (ev) {
      if (ev.target === modal) destroyModal();
    });

    // trap Escape key
    function escHandler(ev) {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        destroyModal();
      }
    }
    document.addEventListener('keydown', escHandler);

    // store handlers on element for cleanup
    modal._rmc_handlers = { handleCalculate, handleInsert, handleClose, escHandler };
  }

  function openModal() {
    // create on demand
    createModal();
    const modal = document.getElementById(MODAL_ID);
    if (!modal) return;
    modal.style.display = 'flex';
    // focus first input
    const input = document.getElementById('calc-length');
    if (input) input.focus();
  }

  function destroyModal() {
    const modal = document.getElementById(MODAL_ID);
    if (!modal) return;
    // remove bound event listeners if stored
    try {
      const h = modal._rmc_handlers || {};
      const calculateBtn = document.getElementById('calc-calculate');
      const insertBtn = document.getElementById('calc-insert');
      const closeBtn = document.getElementById('calc-close');

      if (calculateBtn && h.handleCalculate) calculateBtn.removeEventListener('click', h.handleCalculate);
      if (insertBtn && h.handleInsert) insertBtn.removeEventListener('click', h.handleInsert);
      if (closeBtn && h.handleClose) closeBtn.removeEventListener('click', h.handleClose);
      if (h.escHandler) document.removeEventListener('keydown', h.escHandler);
    } catch (e) {
      /* ignore cleanup errors */
    }
    // remove DOM
    modal.remove();
  }

  // bind open button on DOM ready (idempotent)
  function bindOpenButton() {
    const btn = document.getElementById(OPEN_BTN_ID);
    if (!btn) return;
    // prevent double-binding
    if (btn._rmc_bound) return;
    btn._rmc_bound = true;
    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      openModal();
    });
  }

  let calculatorInitialized = false;

  function initRmcCalculator() {
    if (calculatorInitialized) {
      return;
    }
    calculatorInitialized = true;

    setupLocationBinding();

    refreshAllTemplateSelects()
      .then(function () {
        var gradeSelectAfterRefresh = document.getElementById('grade_select');
        if (gradeSelectAfterRefresh && gradeSelectAfterRefresh.value) {
          populateVariants(gradeSelectAfterRefresh.value);
        }
      })
      .catch(function () {
        /* ignore template fetch errors during init */
      });

    bindOpenButton();

    const gradeSelect = document.getElementById('grade_select');
    if (gradeSelect && !gradeSelect._rmcChangeBound) {
      gradeSelect.addEventListener('change', function () {
        populateVariants(this.value);
      });
      gradeSelect._rmcChangeBound = true;
    }
    if (gradeSelect && gradeSelect.value) {
      populateVariants(gradeSelect.value);
    }

    const volumeField = document.getElementById('rmc_volume');
    if (volumeField && !volumeField._rmcBound) {
      volumeField.addEventListener('change', function () {
        var sel = document.getElementById('variant_select');
        var gradeSel = document.getElementById('grade_select');
        var qty = this.value;
        if (sel && sel.value) {
          showVariantPrice(sel.value, qty);
        } else if (gradeSel && gradeSel.value) {
          var volumeValue = parseFloat(qty || 0) || 0;
          const payload = { product_tmpl_id: gradeSel.value, qty: qty };
          Object.assign(payload, getLocationOverrides());
          jsonRpcCall(PRICE_ENDPOINT, payload, Date.now())
            .then(function (data) {
              updatePriceSummary(data, null, volumeValue);
            })
            .catch(function () {
              updatePriceSummary(null, null);
            });
        }
      });
      volumeField._rmcBound = true;
    }

    const calcBtnPage = document.getElementById('calculate_quote_btn');
    if (calcBtnPage && !calcBtnPage._rmcBound) {
      calcBtnPage.addEventListener('click', function (ev) {
        ev.preventDefault();
        const autoTrigger = this._rmcAutoTrigger;
        this._rmcAutoTrigger = false;

        if (!autoTrigger && window.rmcLocationManager) {
          const desiredCity = cityInputRef && cityInputRef.value ? cityInputRef.value.trim() : '';
          const desiredZip = zipInputRef && zipInputRef.value ? zipInputRef.value.trim() : '';
          const managerCity = (window.rmcLocationManager.state && window.rmcLocationManager.state.city) || '';
          const managerZip = (window.rmcLocationManager.state && window.rmcLocationManager.state.zip) || '';
          const needsSync =
            (desiredCity && desiredCity.toLowerCase() !== managerCity.toLowerCase()) ||
            (desiredZip && desiredZip !== managerZip);
          if (needsSync) {
            syncAndRefresh('manual');
            return;
          }
        }

        const gradeSel = document.getElementById('grade_select');
        const variantSel = document.getElementById('variant_select');
        const volumeFieldLocal = document.getElementById('rmc_volume');
        const qty = volumeFieldLocal && volumeFieldLocal.value ? parseFloat(volumeFieldLocal.value) : 0;
        const tmplId = gradeSel && gradeSel.value ? gradeSel.value : null;
        const variantId = variantSel && variantSel.value ? variantSel.value : null;

        if (!tmplId || !qty || qty <= 0) {
          alert('Please select a grade and enter volume (m³) before calculating quote.');
          return;
        }

        const payload = variantId
          ? { product_id: variantId, qty: qty }
          : { product_tmpl_id: tmplId, qty: qty };
        Object.assign(payload, getLocationOverrides());

        jsonRpcCall(PRICE_ENDPOINT, payload, Date.now())
          .then(function (data) {
            updatePriceSummary(data, null, qty);
            var widget = document.getElementById('rmc-calculator-widget');
            if (widget) widget.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          })
          .catch(function () {
            alert('Failed to calculate quote. Please try again.');
          });
      });
      calcBtnPage._rmcBound = true;
    }

    const addToCartBtn = document.getElementById('add_to_cart_rmc');
    if (addToCartBtn && !addToCartBtn._rmcBound) {
      addToCartBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        const variantSel = document.getElementById('variant_select');
        const gradeSel = document.getElementById('grade_select');
        const volumeFieldLocal = document.getElementById('rmc_volume');
        const qty = volumeFieldLocal && volumeFieldLocal.value ? volumeFieldLocal.value : null;
        const tmplId = gradeSel && gradeSel.value ? gradeSel.value : null;
        const variantId = variantSel && variantSel.value ? variantSel.value : null;
        if (!tmplId || !qty) {
          alert('Please select a grade and calculate volume before adding to cart.');
          return;
        }
        if (variantId) {
          addToCart(variantId, qty);
          return;
        }
        fetch('/rmc_calculator/variants_http?template_id=' + encodeURIComponent(tmplId))
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data && data.success && Array.isArray(data.variants) && data.variants.length) {
              addToCart(data.variants[0].id, qty);
            } else {
              addToCart(null, qty, tmplId);
            }
          })
          .catch(function () {
            addToCart(null, qty, tmplId);
          });
      });
      addToCartBtn._rmcBound = true;
    }

    const requestQuoteBtn = document.getElementById('request_quote_btn');
    if (requestQuoteBtn && !requestQuoteBtn._rmcBound) {
      requestQuoteBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        const variantSel = document.getElementById('variant_select');
        const gradeSel = document.getElementById('grade_select');
        const volumeFieldLocal = document.getElementById('rmc_volume');
        const qty = volumeFieldLocal && volumeFieldLocal.value ? volumeFieldLocal.value : null;
        const tmplId = gradeSel && gradeSel.value ? gradeSel.value : null;
        const variantId = variantSel && variantSel.value ? variantSel.value : null;
        if (!tmplId || !qty) {
          alert('Please select grade and calculate volume first.');
          return;
        }

        var resolveVariantPromise;
        if (variantId) {
          resolveVariantPromise = Promise.resolve(variantId);
        } else if (window && window.RMC && typeof window.RMC.resolveVariantForTemplate === 'function') {
          resolveVariantPromise = window.RMC.resolveVariantForTemplate(tmplId);
        } else {
          resolveVariantPromise = fetch('/rmc_calculator/variants_http?template_id=' + encodeURIComponent(tmplId))
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (!data || !data.variants || !data.variants.length) return null;
              const brandSel = document.getElementById('brand_select');
              const gradeTypeSel = document.getElementById('grade_type_select');
              const brandFilter = brandSel && brandSel.value ? brandSel.value : null;
              const gradeTypeFilter = gradeTypeSel && gradeTypeSel.value ? gradeTypeSel.value : null;
              for (var i = 0; i < data.variants.length; i++) {
                var v = data.variants[i];
                var brandOk = !brandFilter || v.brand === brandFilter;
                var gradeOk = !gradeTypeFilter || v.grade_type === gradeTypeFilter;
                if (brandOk && gradeOk) {
                  return v.id;
                }
              }
              return data.variants.length === 1 ? data.variants[0].id : null;
            })
            .catch(function () { return null; });
        }

        Promise.resolve(resolveVariantPromise)
          .then(function (resolvedVariant) {
            var locationString = '';
            if (cityInputRef && cityInputRef.value) {
              locationString = cityInputRef.value.trim();
            }
            if (zipInputRef && zipInputRef.value) {
              locationString = (locationString ? locationString + ' ' : '') + zipInputRef.value.trim();
            }
            const payload = {
              product_id: resolvedVariant || null,
              product_tmpl_id: resolvedVariant ? null : tmplId,
              qty: qty,
              volume: qty,
              location: locationString || null,
              city: cityInputRef && cityInputRef.value ? cityInputRef.value.trim() : null,
              zip: zipInputRef && zipInputRef.value ? zipInputRef.value.trim() : null,
            };
            return jsonRpcCall('/rmc_calculator/request_quote', payload, 1);
          })
          .then(function (resp) {
            if (resp && resp.success) {
              if (resp.report_url) {
                enableDownloadButton(resp.report_url, 'quote_' + (resp.order_id || 'quote') + '.pdf');
                try { window.open(resp.report_url, '_blank'); } catch (e) { window.location.href = resp.report_url; }
              }
              alert('Thank you for your request. Our team will get back to you shortly.');
            } else {
              alert('Failed to request quote.');
            }
          })
          .catch(function (err) {
            console.error('request_quote error', err);
            var errorMsg = 'Request failed. Please try again.';
            if (err && err.message) {
              errorMsg += '\nError: ' + err.message;
            }
            if (err && err.data && err.data.message) {
              errorMsg += '\nDetails: ' + err.data.message;
            }
            alert(errorMsg);
          });
      });
      requestQuoteBtn._rmcBound = true;
    }
  }

  function runWhenReady(callback) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback, { once: true });
    } else {
      callback();
    }
  }

  runWhenReady(initRmcCalculator);

  // populateVariants helper
  function populateVariants(tmplId) {
    const variantSel = document.getElementById('variant_select');
    if (!variantSel) return;
  // Preserve current filter + selection state
  var prevVariant = variantSel.value || '';
  var prevBrand = (document.getElementById('brand_select') || {}).value || '';
  var prevGradeType = (document.getElementById('grade_type_select') || {}).value || '';

  variantSel.innerHTML = '<option value="">Select variant (optional)</option>';
  if (!tmplId) return;
    fetch(`/rmc_calculator/variants_http?template_id=${tmplId}`)
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        var sel = document.getElementById('variant_select');
        var brandSel = document.getElementById('brand_select');
        var gradeTypeSel = document.getElementById('grade_type_select');

  // reset but keep placeholders
  sel.innerHTML = '<option value="">Select variant (optional)</option>';
  brandSel.innerHTML = '<option value="">All brands</option>';
  gradeTypeSel.innerHTML = '<option value="">All grade types</option>';

        // collect distinct brands and grade_types
        var brands = new Set();
        var gradeTypes = new Set();

        data.variants.forEach(function (v) {
          var opt = document.createElement('option');
          opt.value = v.id;
          opt.text = v.name + (v.brand ? (' - ' + v.brand) : '') + (v.grade_type ? (' - ' + v.grade_type) : '');
          opt._meta = { brand: v.brand, grade_type: v.grade_type, price: v.price, list_price: v.list_price };
          opt.dataset.brand = v.brand || '';
          opt.dataset.gradeType = v.grade_type || '';
          sel.appendChild(opt);

          if (v.brand) { brands.add(v.brand); }
          if (v.grade_type) { gradeTypes.add(v.grade_type); }
        });

        // populate brand and grade selects
        Array.from(brands).sort().forEach(function (b) {
          var o = document.createElement('option'); o.value = b; o.text = b; brandSel.appendChild(o);
        });
        Array.from(gradeTypes).sort().forEach(function (g) {
          var o = document.createElement('option'); o.value = g; o.text = g; gradeTypeSel.appendChild(o);
        });

        // restore previous filter selections if still valid
        if (prevBrand && brands.has(prevBrand)) brandSel.value = prevBrand; else brandSel.value = '';
        if (prevGradeType && gradeTypes.has(prevGradeType)) gradeTypeSel.value = prevGradeType; else gradeTypeSel.value = '';

        // attach filtering handlers - always keep variant select hidden, but maintain selection
        function filterVariants() {
          var b = brandSel.value;
          var g = gradeTypeSel.value;
          var lastMatch = null;
          for (var i = 0; i < sel.options.length; i++) {
            var option = sel.options[i];
            if (!option.value) continue; // placeholder
            var ob = option.dataset.brand || '';
            var og = option.dataset.gradeType || '';
            var matches = true;
            if (b && ob !== b) { matches = false; }
            if (g && og !== g) { matches = false; }
            if (matches) lastMatch = option;
          }
          // if a match was found, set it as selected; otherwise clear selection
          if (lastMatch) {
            sel.value = lastMatch.value;
          } else {
            sel.value = '';
          }
          // keep variant select hidden visually but ensure details reflect selection
          sel.style.display = 'none';
    ensureVariantDetails();
    // update displayed unit price for the currently selected variant
    var curVid = sel.value || null;
    var volEl = document.getElementById('rmc_volume');
    var qtyForPrice = volEl && volEl.value ? volEl.value : null;
    if (curVid) showVariantPrice(curVid, qtyForPrice);
        }
        // Avoid double-binding
        if (!brandSel._boundVariantFilter) { brandSel.addEventListener('change', filterVariants); brandSel._boundVariantFilter = true; }
        if (!gradeTypeSel._boundVariantFilter) { gradeTypeSel.addEventListener('change', filterVariants); gradeTypeSel._boundVariantFilter = true; }

        // Always hide the variant select UI (we resolve variants programmatically)
        sel.style.display = 'none';
        // Apply current filters immediately
        filterVariants();
        // try restore variant selection if still exists under current filter
        if (prevVariant && sel.querySelector('option[value="' + prevVariant + '"]')) {
          sel.value = prevVariant;
        }
        ensureVariantDetails();
      })
    .catch(function (err) { console.error('variants fetch error', err); });
  }

  // helper: submit standard add-to-cart form to /shop/cart/update
  // Ensure a details box exists for showing Brand / Grade Type
  function ensureVariantDetails() {
    var sel = document.getElementById('variant_select');
    if (!sel) return;
    var container = sel.parentNode;
    if (!container) return;
    var details = document.getElementById('variant_details');
    if (!details) {
      details = document.createElement('div');
      details.id = 'variant_details';
      details.style.cssText = 'margin-top:6px; font-size:0.95em; color:#333;';
      sel.insertAdjacentElement('afterend', details);
    }
    // update current selection
    updateVariantDetails(sel);
    // also show price for current selection
    var cur = sel && sel.value ? sel.value : null;
    var volEl = document.getElementById('rmc_volume');
    var qtyForPrice = volEl && volEl.value ? volEl.value : null;
    if (cur) showVariantPrice(cur, qtyForPrice);
  }

  // fetch and display current unit price for a variant (qty optional)
  function showVariantPrice(variantId, qty) {
    var priceEl = document.getElementById('variant_price');
    if (!variantId) {
      if (priceEl) priceEl.textContent = 'Unit price: —';
      updatePriceSummary(null, null);
      return;
    }
    var payload = { product_id: variantId };
    if (qty) payload.qty = qty;
    Object.assign(payload, getLocationOverrides());

    function getVariantMeta(id) {
      var sel = document.getElementById('variant_select');
      if (!sel) return null;
      var opt = sel.querySelector('option[value="' + id + '"]');
      return (opt && opt._meta) ? opt._meta : null;
    }

    function fallbackSummary() {
      var meta = getVariantMeta(variantId);
      var vol = parseFloat(qty || 0) || parseFloat((document.getElementById('rmc_volume') || {}).value) || 0;
      if (!meta || (!meta.price && !meta.list_price)) {
        updatePriceSummary(null, null);
        return;
      }
      var fallback = parseFloat(meta.price || meta.list_price) || 0;
      updatePriceSummary({
        success: true,
        currency: 'INR',
        price: fallback,
        base_price: fallback * vol,
        computed_price: fallback * vol,
        discount_value: 0,
        truck_count: vol ? Math.ceil(vol / TRUCK_CAP_M3) : 0,
      }, null, vol);
    }

    jsonRpcCall(PRICE_ENDPOINT, payload, Date.now())
      .then(function (summary) {
        if (summary && summary.success) {
          updatePriceSummary(summary, null, qty);
        } else {
          fallbackSummary();
        }
      })
      .catch(function () {
        fallbackSummary();
      });
  }


  function updateVariantDetails(sel) {
    if (!sel) return;
    var details = document.getElementById('variant_details');
    if (!details) return;
    var opt = sel.options[sel.selectedIndex];
    if (!opt || !opt._meta) {
      details.innerHTML = '';
      return;
    }
    var parts = [];
    if (opt._meta.brand) parts.push('<strong>Brand:</strong> ' + (opt._meta.brand || '—'));
    if (opt._meta.grade_type) parts.push('<strong>Grade Type:</strong> ' + (opt._meta.grade_type || '—'));
    details.innerHTML = parts.join(' &nbsp; | &nbsp; ');
  }

  function attachVariantChangeHandler() {
    var sel = document.getElementById('variant_select');
    if (!sel) return;
    if (sel._brand_bound) return;
    sel._brand_bound = true;
    sel.addEventListener('change', function () { updateVariantDetails(sel); });
  }

  function ensureDownloadButton() {
    var container = document.getElementById('rmc-calculator-widget') || document.body;
    if (!container) return null;
    var existing = document.getElementById('download_quote_pdf');
    if (existing) return existing;
    var a = document.createElement('a');
    a.id = 'download_quote_pdf';
    a.textContent = 'Download Quote PDF';
    a.className = 'btn btn-outline-primary';
    // visible but disabled until a report url is available
    a.style.cssText = 'display:inline-block; margin-left:8px; padding:6px 10px; opacity:0.6; pointer-events:none;';
    a.href = '#';
    a.target = '_blank';
    a.setAttribute('aria-disabled', 'true');
    // clicking a disabled button does nothing; when enabled we'll set download attribute
    a.addEventListener('click', function (ev) {
      if (a.getAttribute('aria-disabled') === 'true') ev.preventDefault();
    });
    container.appendChild(a);
    return a;
  }

  // enable and configure the download button with a valid report_url
  function enableDownloadButton(reportUrl, filename) {
    if (!reportUrl) return null;
    var btn = ensureDownloadButton();
    if (!btn) return null;
    btn.href = reportUrl;
    btn.style.opacity = '1';
    btn.style.pointerEvents = 'auto';
    btn.setAttribute('aria-disabled', 'false');
    // set download filename if provided (browser may ignore cross-origin blobs)
    if (filename) btn.setAttribute('download', filename);
    // ensure it opens in a new tab for servers that return Content-Disposition inline
    btn.target = '_blank';
    return btn;
  }
  function addToCart(product_id, qty, product_tmpl_id) {
    // prefer DOM values when not provided
    if (!product_id && !product_tmpl_id) {
      var variantSel = document.getElementById('variant_select');
      if (variantSel && variantSel.value) product_id = variantSel.value;
    }
    if (!qty) {
      var volEl = document.getElementById('rmc_volume');
      if (volEl && volEl.value) qty = volEl.value;
    }
    if (!product_id && !product_tmpl_id) return;
    if (!qty) return;

    // create CRM lead (best-effort) before adding to cart
    try {
      var leadPayload = {
        product_id: product_id || null,
        product_tmpl_id: product_tmpl_id || null,
        qty: qty,
        city: cityInputRef && cityInputRef.value ? cityInputRef.value.trim() : null,
        zip: zipInputRef && zipInputRef.value ? zipInputRef.value.trim() : null,
      };
      fetch('/rmc_calculator/create_lead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(leadPayload)
      }).catch(function () { /* ignore create_lead failures */ });
    } catch (e) {
      /* ignore */
    }

    // if we have a variant id, add to cart using form submission
    if (product_id) {
      console.log('Adding to cart - product_id:', product_id, 'qty:', qty);

      // Create a hidden form and submit it with express=1 to bypass CSRF check
      var form = document.createElement('form');
      form.method = 'POST';
      form.action = '/rmc/cart/add';
      form.style.display = 'none';

      // Add product_id field
      var pidInput = document.createElement('input');
      pidInput.type = 'hidden';
      pidInput.name = 'product_id';
      pidInput.value = product_id;
      form.appendChild(pidInput);

      // Add add_qty field
      var qtyInput = document.createElement('input');
      qtyInput.type = 'hidden';
      qtyInput.name = 'add_qty';
      qtyInput.value = qty;
      form.appendChild(qtyInput);

      // Add CSRF token
      var csrfToken = '';
      if (window.odoo && window.odoo.csrf_token) {
        csrfToken = window.odoo.csrf_token;
      } else {
        var csrfMeta = document.querySelector('meta[name="csrf-token"]');
        if (csrfMeta) {
          csrfToken = csrfMeta.getAttribute('content');
        }
      }

      if (csrfToken) {
        var csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrf_token';
        csrfInput.value = csrfToken;
        form.appendChild(csrfInput);
      }

      // Append form to body and submit
      document.body.appendChild(form);
      form.submit();
      return;
    }
    // helper: resolve a variant id for a template, preferring current brand/grade selections
    function resolveVariantForTemplate(tmplId) {
      return new Promise(function (resolve) {
        if (!tmplId) return resolve(null);
        // prefer any selection in hidden variant select
        var sel = document.getElementById('variant_select');
        if (sel && sel.value) return resolve(sel.value);
        // else use brand/grade selections
        var brand = (document.getElementById('brand_select') || {}).value || null;
        var gradeType = (document.getElementById('grade_type_select') || {}).value || null;
        // fetch variants and pick the best match
        fetch('/rmc_calculator/variants_http?template_id=' + encodeURIComponent(tmplId)).then(function (r) { return r.json(); }).then(function (data) {
          if (!data || !data.variants || !data.variants.length) return resolve(null);
          // try to find exact brand+grade match
          var found = null;
          for (var i = 0; i < data.variants.length; i++) {
            var v = data.variants[i];
            var matches = true;
            if (brand && v.brand !== brand) matches = false;
            if (gradeType && v.grade_type !== gradeType) matches = false;
            if (matches) { found = v; break; }
          }
          if (found) return resolve(found.id);
          // fallback: if only one variant exists, use it
          if (data.variants.length === 1) return resolve(data.variants[0].id);
          // otherwise, resolve null (no variant resolved)
          return resolve(null);
        }).catch(function () { resolve(null); });
      });
    }

    // otherwise resolve first variant for the template and submit
    resolveVariantForTemplate(product_tmpl_id).then(function (vid) {
      if (!vid) return; // nothing to add
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/shop/cart/update';
      form.style.display = 'none';
      const pid = document.createElement('input'); pid.type = 'hidden'; pid.name = 'product_id'; pid.value = vid;
      const addq = document.createElement('input'); addq.type = 'hidden'; addq.name = 'add_qty'; addq.value = qty;
      var csrfVal = '';
      if (window.odoo && window.odoo.csrf_token) csrfVal = window.odoo.csrf_token;
      else {
        var el = document.querySelector('input[name="csrf_token"]');
        if (el) csrfVal = el.value;
      }
      const csrfIn = document.createElement('input'); csrfIn.type = 'hidden'; csrfIn.name = 'csrf_token'; csrfIn.value = csrfVal;
      form.appendChild(pid); form.appendChild(addq);
      form.appendChild(csrfIn);
      document.body.appendChild(form);
      form.submit();
      // Redirect to cart after submission
      setTimeout(function() { window.location.href = '/shop/cart'; }, 100);
    }).catch(function () { /* ignore */ });
  // end of addToCart
  }

  // expose to window for manual control (optional)
  window.RMC = window.RMC || {};
  window.RMC.openCalculator = openModal;
  window.RMC.destroyCalculator = destroyModal;
  // expose variant resolver for reuse
  window.RMC.resolveVariantForTemplate = function (tmplId) {
    return new Promise(function (resolve) {
      if (!tmplId) return resolve(null);
      fetch('/rmc_calculator/variants_http?template_id=' + encodeURIComponent(tmplId)).then(function (r) { return r.json(); }).then(function (data) {
        if (!data || !data.variants || !data.variants.length) return resolve(null);
        var b = (document.getElementById('brand_select') || {}).value || null;
        var g = (document.getElementById('grade_type_select') || {}).value || null;
        for (var i = 0; i < data.variants.length; i++) {
          var v = data.variants[i];
          var ok = true;
          if (b && v.brand !== b) ok = false;
          if (g && v.grade_type !== g) ok = false;
          if (ok) return resolve(v.id);
        }
        if (data.variants.length === 1) return resolve(data.variants[0].id);
        return resolve(null);
      }).catch(function () { resolve(null); });
    });
  };

  runWhenReady(function () { setTimeout(initFallbackRMCSelects, 0); });

  function initFallbackRMCSelects() {
    if (document.getElementById('grade_select')) return;
    var btn = document.getElementById('open_dim_popup');
    if (!btn) return;
    var container = document.createElement('div');
    container.id = 'rmc_fallback_selects';
    container.style.cssText = 'margin-bottom:12px;';
    container.innerHTML = '<label style="display:block; font-weight:600;">Concrete Grade</label>'+
      '<select id="grade_select" class="form-control" data-placeholder="Select concrete grade" style="max-width:260px; margin-bottom:6px;"><option value="">Loading...</option></select>'+
      '<label style="display:block; font-weight:600;">Brand</label>'+
      '<select id="brand_select" class="form-control" style="max-width:260px; margin-bottom:6px;"><option value="">All brands</option></select>'+
      '<label style="display:block; font-weight:600;">Grade Type</label>'+
      '<select id="grade_type_select" class="form-control" style="max-width:260px; margin-bottom:6px;"><option value="">All grade types</option></select>'+
      '<select id="variant_select" class="form-control" style="display:none; max-width:260px;"><option value="">Select variant (optional)</option></select>'+
      '<div id="variant_details" style="margin-top:6px; font-size:0.9em; color:#333;"></div>';
    var parent = btn.parentNode;
    parent.parentNode.insertBefore(container, parent);
    refreshAllTemplateSelects().then(function (templates) {
      var fallbackGrade = container.querySelector('#grade_select');
      if (fallbackGrade && fallbackGrade.value) {
        populateVariants(fallbackGrade.value);
      }
      var brandSel = container.querySelector('#brand_select');
      var gradeTypeSel = container.querySelector('#grade_type_select');
      if (brandSel && cachedTemplates.length) {
        var brands = new Set();
        cachedTemplates.forEach(function (tmpl) { if (tmpl.brand) brands.add(tmpl.brand); });
        Array.from(brands).sort().forEach(function (b) { var o = document.createElement('option'); o.value = b; o.text = b; brandSel.appendChild(o); });
      }
      if (gradeTypeSel && cachedTemplates.length) {
        var gradeTypes = new Set();
        cachedTemplates.forEach(function (tmpl) { if (tmpl.grade_type) gradeTypes.add(tmpl.grade_type); });
        Array.from(gradeTypes).sort().forEach(function (g) { var o = document.createElement('option'); o.value = g; o.text = g; gradeTypeSel.appendChild(o); });
      }
      if (fallbackGrade) fallbackGrade.addEventListener('change', function () { populateVariants(this.value); });
      if (brandSel) brandSel.addEventListener('change', function () { populateVariants(fallbackGrade && fallbackGrade.value); });
      if (gradeTypeSel) gradeTypeSel.addEventListener('change', function () { populateVariants(fallbackGrade && fallbackGrade.value); });
    });
  }

  } // End of initializeCalculator function
})();
