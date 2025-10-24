odoo.define('rmc_subcontractor_management.landing_page', function (require) {
    "use strict";

    const publicWidget = require('web.public.widget');

    publicWidget.registry.SubcontractorCalculator = publicWidget.Widget.extend({
        selector: '.o_subc_landing',
        events: {
            'input #subcCalcCity': '_onInputChanged',
            'input #subcCalcCapacity': '_onInputChanged',
            'input #subcCalcMixers': '_onInputChanged',
        },

        start() {
            this._updateOutput();
            return this._super(...arguments);
        },

        _onInputChanged() {
            this._updateOutput();
        },

        _updateOutput() {
            const capacity = parseFloat(this.el.querySelector('#subcCalcCapacity')?.value || 0);
            const mixers = parseInt(this.el.querySelector('#subcCalcMixers')?.value || 0, 10);
            const monthlyVolume = capacity * 8 * 26; // 8 hours shift, 26 days
            const revenue = monthlyVolume * 350; // indicative rate
            const volumeNode = this.el.querySelector('#subcCalcVolume');
            const revenueNode = this.el.querySelector('#subcCalcRevenue');
            if (volumeNode) {
                volumeNode.textContent = `${Math.round(monthlyVolume).toLocaleString()} m³`;
            }
            if (revenueNode) {
                revenueNode.textContent = `₹${Math.round(revenue).toLocaleString()}`;
            }
        },
    });

    return publicWidget.registry.SubcontractorCalculator;
});
