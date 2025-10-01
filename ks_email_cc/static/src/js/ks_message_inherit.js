/** @odoo-module **/

import { Message } from "@mail/core/common/message_model";
import { patch } from "@web/core/utils/patch";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        this.ks_cc_partners = this.ks_cc_partners || false;
        this.ks_bcc_partners = this.ks_bcc_partners || false;
        this.ks_email_cc_string = this.ks_email_cc_string || false;
        this.ks_email_bcc_string = this.ks_email_bcc_string || false;
    },
});
