/** @odoo-module **/
import { Chatter } from "@mail/components/chatter/chatter";
import { useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";
patch(Chatter.prototype, "odupilot.chatter", {
    setup() {
        this._super(...arguments);
        useBus(this.env.bus, "odupilot/chatter", ({ detail }) => {
            if (detail.model === this.chatter.thread.model && detail.id === this.chatter.thread.id) { this.chatter.thread.refresh(); }
        });
    },
    get hasAskAiButton() {
        return Boolean(session.odupilot_available && this.chatter.thread.id && this.chatter.thread.model !== "mail.channel");
    },
    onClickAskAi() {
        return this.env.services.action.doAction({
            type: "ir.actions.act_window", name: _t("Ask AI"),
            res_model: "odupilot.ask.wizard", views: [[false, "form"]], target: "new",
            context: { default_res_model: this.chatter.thread.model, default_res_id: this.chatter.thread.id },
        }, { onClose: () => this.chatter.thread.refresh() });
    },
});
