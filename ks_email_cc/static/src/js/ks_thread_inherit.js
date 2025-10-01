/** @odoo-module **/

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";

patch(Thread.prototype, {
    async performRpcMessagePost(postData) {
        if (postData.subtype_xmlid === 'mail.mt_comment') {
            if (postData.context) {
                postData.context.ks_from_button = true;
            } else {
                postData.context = { ks_from_button: true };
            }
        }
        return super.performRpcMessagePost(...arguments);
    }
});
