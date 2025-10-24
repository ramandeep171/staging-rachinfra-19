odoo.define('rmc_subcontractor_management.portal_dashboard', function (require) {
    "use strict";

    const publicWidget = require('web.public.widget');

    publicWidget.registry.SubcontractorPortalDashboard = publicWidget.Widget.extend({
        selector: '.o_subc_portal',
        start() {
            this._renderProgressRing();
            return this._super(...arguments);
        },

        _renderProgressRing() {
            const ring = this.el.querySelector('.o_progress_ring');
            if (!ring) {
                return;
            }
            const progress = parseFloat(ring.dataset.progress || 0);
            ring.style.background = `conic-gradient(#22c55e ${progress * 3.6}deg, rgba(255,255,255,0.2) ${progress * 3.6}deg)`;
        },
    });

    return publicWidget.registry.SubcontractorPortalDashboard;
});
