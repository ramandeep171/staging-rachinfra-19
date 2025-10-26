/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { _t } from "@web/core/l10n/translation";

const COOKIE_KEYS = {
    city: "ri_loc_city",
    zip: "ri_loc_zip",
    method: "ri_loc_method",
};

const ENDPOINTS = {
    save: "/rmc/location/save",
    ipGuess: "/rmc/location/ip_guess",
    reverse: "/rmc/location/reverse",
    checkout: "/rmc/location/checkout_sync",
};

function readCookie(name) {
    return document.cookie
        .split(";")
        .map((item) => item.trim())
        .filter((item) => item.startsWith(`${name}=`))
        .map((item) => decodeURIComponent(item.split("=")[1] || ""))
        .shift() || "";
}

async function fetchJson(url, options = {}) {
    const opts = {
        credentials: "same-origin",
        headers: {
            Accept: "application/json",
        },
        ...options,
    };
    if (opts.method && opts.method.toUpperCase() !== "GET") {
        opts.headers["Content-Type"] = "application/json";
    }
    try {
        const response = await fetch(url, opts);
        if (!response.ok) {
            throw new Error(_t("Server responded with an error (%(status)s).", { status: response.status }));
        }
        return await response.json();
    } catch (error) {
        console.warn("[rmc_location_detector] request failed", error);
        throw error;
    }
}

publicWidget.registry.RmcLocationDetector = publicWidget.Widget.extend({
    selector: "#wrapwrap",

    start() {
        this.$chip = $(document.getElementById("rmc_location_chip"));
        if (!this.$chip.length) {
            return this._super(...arguments);
        }
        this._defaultParent = this.$chip[0].parentElement;
        this._defaultNextSibling = this.$chip[0].nextElementSibling;

        this.state = {
            city: "",
            zip: "",
            method: "",
            pricelistName: "",
        };

        this.$banner = $(document.getElementById("rmcLocationBanner"));
        this.defaultCityText = this.$chip.data("default-city") || _t("Detecting location…");
        this.ipHintText = this.$chip.data("tooltip-ip") || _t("Approximate. Improve using GPS.");
        this.enableIp = this._isTruthy(this.$chip.data("enable-ip"));
        this.enableGps = this._isTruthy(this.$chip.data("enable-gps")) && Boolean(navigator.geolocation);

        this.cityEl = this.$chip.find(".rmc-location-city")[0];
        this.zipEl = this.$chip.find(".rmc-location-zip")[0];
        this.hintEl = this.$chip.find(".rmc-location-method-hint")[0];

        this.$modal = $(document.getElementById("rmcLocationModal"));
        this.$form = this.$modal.find(".rmc-location-form");
        this.$cityInput = this.$form.find('input[name="city"]');
        this.$zipInput = this.$form.find('input[name="zip"]');
        this.$error = this.$modal.find(".rmc-location-error");
        this.$gpsBtn = this.$modal.find(".rmc-location-gps");
        this.$gpsLabel = this.$modal.find(".rmc-location-gps-label");
        this.$saveBtn = this.$modal.find(".rmc-location-save");
        this.$saveLabel = this.$modal.find(".rmc-location-save-label");

        this.modalInstance = null;
        this._manualKeydownHandler = null;
        if (this.$modal.length) {
            if (window.bootstrap && window.bootstrap.Modal) {
                this.modalInstance = new window.bootstrap.Modal(this.$modal[0], {
                    backdrop: "static",
                    keyboard: true,
                });
            } else if (this.$modal.modal) {
                // Fallback to bootstrap jQuery plugin if global bootstrap namespace isn't available.
                this.$modal.modal({
                    backdrop: "static",
                    keyboard: true,
                    show: false,
                });
                this.modalInstance = {
                    show: () => this.$modal.modal("show"),
                    hide: () => this.$modal.modal("hide"),
                };
            }
            this.$modal.on("hidden.bs.modal", () => this._clearError());
            this.$modal.on("click", "[data-bs-dismiss='modal']", (ev) => {
                if (!this.modalInstance) {
                    ev.preventDefault();
                    this._hideModalManually();
                }
            });
        }

        this.$chip.on("click", "[data-action='rmc-open-modal']", this._openModal.bind(this));
        this.$chip.on("click", (ev) => {
            if (!$(ev.target).closest("[data-action='rmc-open-modal']").length) {
                this._openModal(ev);
            }
        });
        this._onResize = this._onResize.bind(this);
        window.addEventListener("resize", this._onResize, { passive: true });
        this.$form.on("submit", this._submitForm.bind(this));
        this.$gpsBtn.on("click", this._useGps.bind(this));

        if (!this.enableGps) {
            this.$gpsBtn.addClass("d-none");
        }

        this._placeChip();
        this._renderChipPlaceholder();
        this._loadFromCookies();

        if (!this.state.city && !this.state.zip && this.enableIp) {
            this._fetchIpGuess();
        }

        this._watchCheckoutZip();
        window.rmcSyncCheckout = (zip, city = "") => this._syncCheckout(zip, city);

        return this._super(...arguments);
    },

    destroy() {
        window.removeEventListener("resize", this._onResize);
        window.clearTimeout(this._resizeTimer);
        return this._super(...arguments);
    },

    // --------------------------------------------------------------------------
    // Helpers
    // --------------------------------------------------------------------------

    _isTruthy(value) {
        if (value === undefined || value === null) {
            return false;
        }
        if (typeof value === "boolean") {
            return value;
        }
        return String(value) !== "0" && String(value).toLowerCase() !== "false";
    },

    _renderChipPlaceholder() {
        if (this.cityEl) {
            this.cityEl.textContent = this.defaultCityText;
        }
        if (this.zipEl) {
            this.zipEl.textContent = "";
        }
        if (this.hintEl) {
            this.hintEl.classList.add("d-none");
        }
    },

    _placeChip() {
        const chipEl = this.$chip[0];
        if (!chipEl) {
            return;
        }
        const isDesktop = window.innerWidth >= 992;
        if (isDesktop) {
            const targets = [
                document.querySelector("header .navbar-nav.align-items-center"),
                document.querySelector("header .navbar-nav"),
                document.querySelector("header nav"),
            ];
            for (const target of targets) {
                if (target && target !== chipEl.parentElement) {
                    target.appendChild(chipEl);
                    return;
                }
            }
        } else if (this._defaultParent) {
            if (chipEl.parentElement !== this._defaultParent) {
                if (this._defaultNextSibling && this._defaultNextSibling.parentElement === this._defaultParent) {
                    this._defaultParent.insertBefore(chipEl, this._defaultNextSibling);
                } else {
                    this._defaultParent.appendChild(chipEl);
                }
            }
        }
    },

    _loadFromCookies() {
        const city = readCookie(COOKIE_KEYS.city);
        const zip = readCookie(COOKIE_KEYS.zip);
        const method = readCookie(COOKIE_KEYS.method);
        if (city || zip) {
            this._updateState({ city, zip, method });
        }
    },

    _updateState({ city, zip, method, pricelistName }) {
        this.state.city = city || "";
        this.state.zip = zip || "";
        this.state.method = method || "";
        this.state.pricelistName = pricelistName || "";
        this._renderChip();
    },

    _renderChip() {
        if (this.cityEl) {
            this.cityEl.textContent = this.state.city || this.defaultCityText;
        }
        if (this.zipEl) {
            this.zipEl.textContent = this.state.zip ? ` ${this.state.zip}` : "";
        }
        if (this.hintEl) {
            if (this.state.method === "ip") {
                this.hintEl.textContent = this.ipHintText;
                this.hintEl.classList.remove("d-none");
            } else {
                this.hintEl.textContent = "";
                this.hintEl.classList.add("d-none");
            }
        }
    },

    _openModal(event) {
        event.preventDefault();
        this._clearError();
        this.$cityInput.val(this.state.city);
        this.$zipInput.val(this.state.zip);
        this._setGpsLoading(false);
        this._setSaveLoading(false);
        if (this.modalInstance) {
            this.modalInstance.show();
            this.$modal.one("shown.bs.modal", () => this.$cityInput.trigger("focus"));
        } else if (this.$modal.length) {
            this._showModalManually();
        }
    },

    _submitForm(event) {
        event.preventDefault();
        if (this.$saveBtn.prop("disabled")) {
            return;
        }
        const city = (this.$cityInput.val() || "").toString().trim();
        const zip = (this.$zipInput.val() || "").toString().trim();
        this._setSaveLoading(true);
        this._clearError();
        this._saveLocation({ city, zip, method: "manual" })
            .then(() => {
                if (this.modalInstance) {
                    this.modalInstance.hide();
                } else if (this.$modal.length) {
                    this._hideModalManually();
                }
            })
            .catch((error) => {
                this._showError(error.message || _t("We could not update your location."));
            })
            .finally(() => {
                this._setSaveLoading(false);
            });
    },

    async _saveLocation(payload, options = {}) {
        const response = await fetchJson(ENDPOINTS.save, {
            method: "POST",
            body: JSON.stringify(payload),
        });
        const opts = {
            reloadOnReprice: true,
            showBanner: true,
            autoClose: false,
            sourceMethod: payload.method,
            updateForm: true,
            ...options,
        };
        this._handleServerResponse(response, opts);
        if (response.error) {
            throw new Error(response.error);
        }
        if (opts.autoClose) {
            window.setTimeout(() => this._closeModal(), 150);
        }
        return response;
    },

    _handleServerResponse(response, options = {}) {
        if (!response) {
            return;
        }
        if (response.error) {
            if (options.showBanner !== false) {
                this._showBanner(response.error, true);
            }
            return;
        }
        const payload = {
            city: response.city,
            zip: response.zip,
            method: response.method || this.state.method,
            pricelistName: response.pricelist_name,
        };
        this._updateState(payload);
        if (options.updateForm !== false) {
            this._prefillForm(payload.city, payload.zip);
        }
        if (response.repriced && options.showBanner !== false) {
            const message = _t("Prices updated for delivery to %(city)s %(zip)s", {
                city: response.city || "",
                zip: response.zip || "",
            }).trim();
            this._showBanner(message);
        }
        if (response.repriced && options.reloadOnReprice) {
            window.setTimeout(() => window.location.reload(), 800);
        }
    },

    _fetchIpGuess() {
        fetchJson(ENDPOINTS.ipGuess)
            .then((response) => {
                if (response && !response.error) {
                    this._handleServerResponse(response, { showBanner: false });
                }
            })
            .catch(() => {
                // Ignore GeoIP failures silently
            });
    },

    _useGps(event) {
        event.preventDefault();
        if (!this.enableGps || this.$gpsBtn.prop("disabled")) {
            return;
        }
        if (!navigator.geolocation) {
            this._showError(_t("GPS is not available on this device."));
            return;
        }
        this._setGpsLoading(true);
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const coords = position.coords || {};
                const params = new URLSearchParams({
                    lat: coords.latitude,
                    lon: coords.longitude,
                });
                fetchJson(`${ENDPOINTS.reverse}?${params.toString()}`)
                    .then((response) => {
                        if (response.error) {
                            throw new Error(response.error);
                        }
                        this._prefillForm(response.city, response.zip);
                        return this._saveLocation({
                            city: response.city,
                            zip: response.zip,
                            method: "gps",
                        }, {
                            autoClose: true,
                            sourceMethod: "gps",
                        });
                    })
                    .catch((error) => {
                        this._showError(error.message || _t("We could not determine your position."));
                    })
                    .finally(() => this._setGpsLoading(false));
            },
            (error) => {
                const message =
                    error.code === error.PERMISSION_DENIED
                        ? _t("GPS permission was denied.")
                        : _t("We could not determine your position.");
                this._showError(message);
                this._setGpsLoading(false);
            },
            {
                enableHighAccuracy: false,
                timeout: 7000,
                maximumAge: 60000,
            }
        );
    },

    _setGpsLoading(isLoading) {
        this.$gpsBtn.prop("disabled", isLoading);
        if (!this.enableGps) {
            return;
        }
        if (this.$gpsLabel.length) {
            this.$gpsLabel.text(isLoading ? _t("Locating…") : _t("Use GPS"));
        }
    },

    _setSaveLoading(isLoading) {
        this.$saveBtn.prop("disabled", isLoading);
        if (this.$saveLabel.length) {
            this.$saveLabel.text(isLoading ? _t("Saving…") : _t("Save"));
        }
    },

    _showError(message) {
        if (!this.$error.length) {
            return;
        }
        this.$error.text(message || "").removeClass("d-none");
    },

    _clearError() {
        if (!this.$error.length) {
            return;
        }
        this.$error.text("").addClass("d-none");
    },

    _onResize() {
        window.clearTimeout(this._resizeTimer);
        this._resizeTimer = window.setTimeout(() => this._placeChip(), 150);
    },

    _showModalManually() {
        this.$modal.addClass("show d-block");
        this.$modal.attr("aria-hidden", "false");
        this.$modal.trigger("focus");
        this.$cityInput.trigger("focus");
        this._injectBackdrop();
    },

    _hideModalManually() {
        this.$modal.removeClass("show d-block");
        this.$modal.attr("aria-hidden", "true");
        this._removeBackdrop();
        this._clearError();
    },

    _injectBackdrop() {
        if (document.querySelector(".rmc-location-backdrop")) {
            return;
        }
        const backdrop = document.createElement("div");
        backdrop.className = "modal-backdrop fade show rmc-location-backdrop";
        backdrop.addEventListener("click", () => this._hideModalManually());
        document.body.appendChild(backdrop);
        this._bindManualKeydown();
    },

    _removeBackdrop() {
        const backdrop = document.querySelector(".rmc-location-backdrop");
        if (backdrop) {
            backdrop.remove();
        }
        this._unbindManualKeydown();
    },

    _bindManualKeydown() {
        if (this._manualKeydownHandler) {
            return;
        }
        this._manualKeydownHandler = (event) => {
            if (event.key === "Escape") {
                this._hideModalManually();
            }
        };
        document.addEventListener("keydown", this._manualKeydownHandler);
    },

    _unbindManualKeydown() {
        if (this._manualKeydownHandler) {
            document.removeEventListener("keydown", this._manualKeydownHandler);
            this._manualKeydownHandler = null;
        }
    },

    _watchCheckoutZip() {
        const $checkoutForm = $("form[name='checkout']");
        if (!$checkoutForm.length) {
            return;
        }
        const $zip = $checkoutForm.find("input[name='zip']");
        if (!$zip.length) {
            return;
        }
        const $city = $checkoutForm.find("input[name='city']");
        let debounceHandle = null;
        const triggerSync = () => {
            const zip = ($zip.val() || "").toString().trim();
            const city = ($city.val() || "").toString().trim();
            window.clearTimeout(debounceHandle);
            debounceHandle = window.setTimeout(() => this._syncCheckout(zip, city), 400);
        };
        $zip.on("change blur", triggerSync);
        $zip.on("keyup", (ev) => {
            if (["Enter", "Tab"].includes(ev.key)) {
                triggerSync();
            }
        });
    },

    _syncCheckout(zip, city = "") {
        fetchJson(ENDPOINTS.checkout, {
            method: "POST",
            body: JSON.stringify({ zip, city }),
        })
            .then((response) => this._handleServerResponse(response, { showBanner: true, reloadOnReprice: false }))
            .catch((error) => this._showBanner(error.message || _t("We could not update the checkout pricing."), true));
    },

    _showBanner(message, isError = false) {
        if (!this.$banner.length || !message) {
            return;
        }
        this.$banner
            .removeClass("d-none alert-info alert-warning")
            .addClass(isError ? "alert-warning" : "alert-info")
            .text(message);
    },

    _prefillForm(city, zip) {
        if (this.$cityInput && this.$cityInput.length && city) {
            this.$cityInput.val(city);
        }
        if (this.$zipInput && this.$zipInput.length && zip) {
            this.$zipInput.val(zip);
        }
    },

    _closeModal() {
        if (this.modalInstance) {
            this.modalInstance.hide();
        } else if (this.$modal.length) {
            this._hideModalManually();
        }
    },
});
