/** @odoo-module **/
import { Chatter } from "@mail/chatter/web_portal/chatter";
import { useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";
patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        useBus(this.env.bus, "odupilot/chatter", ({ detail }) => {
            if (detail.model === this.props.threadModel && detail.id === this.props.threadId) { this.load(this.state.thread, ["messages"]); }
        });
    },
    get hasAskAiButton() {
        return Boolean(session.odupilot_available && this.props.threadId && this.props.threadModel !== "discuss.channel");
    },
    onClickAskAi() {
        return this.env.services.action.doAction({
            type: "ir.actions.act_window", name: _t("Ask AI"),
            res_model: "odupilot.ask.wizard", views: [[false, "form"]], target: "new",
            context: { default_res_model: this.props.threadModel, default_res_id: this.props.threadId },
        }, { onClose: () => this.load(this.state.thread, ["messages"]) });
    },
});
