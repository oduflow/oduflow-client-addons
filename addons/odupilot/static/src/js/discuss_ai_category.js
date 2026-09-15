/** @odoo-module **/
import { Thread } from "@mail/core/common/thread_model";
import { Message } from "@mail/core/common/message_model";
import { DiscussApp } from "@mail/core/public_web/discuss_app_model";
import { DiscussAppCategory } from "@mail/discuss/core/public_web/discuss_app_category_model";
import { Settings } from "@mail/core/common/settings_model";
import { fields } from "@mail/core/common/record";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
patch(Settings.prototype, { setup() { super.setup(...arguments); this.is_discuss_sidebar_category_ai_open = true; } });
patch(DiscussApp.prototype, {
    setup() {
        super.setup(...arguments);
        this.odupilot = fields.One("DiscussAppCategory", {
            compute() { return { id: "odupilot", name: _t("OduPilot"), icon: "fa fa-magic", sequence: 20, hideWhenEmpty: true, serverStateKey: "is_discuss_sidebar_category_ai_open" }; },
            eager: true,
        });
    },
});
patch(DiscussAppCategory.prototype, {
    sortThreads(a, b) { return this.id === "odupilot" ? b.id - a.id : super.sortThreads(a, b); },
});
const replyNotifications = new Map();
function dismissReply(thread) {
    replyNotifications.get(thread.id)?.();
    replyNotifications.delete(thread.id);
}
patch(Thread.prototype, {
    get inChathubOnNewMessage() { return !this.odupilot_session?.discuss_only && super.inChathubOnNewMessage; },
    async notifyMessageToUser(message) {
        if (message.odupilot_step) { return; }
        await super.notifyMessageToUser(...arguments);
        if (message.odupilot_assistant && !this.isDisplayed && !this.self_member_id?.mute_until_dt) {
            dismissReply(this);
            const document = new DOMParser().parseFromString(String(message.body || ""), "text/html");
            for (const trace of document.querySelectorAll(".o_AiChatTrace")) { trace.remove(); }
            replyNotifications.set(this.id, this.store.env.services.notification.add(
                document.body.textContent.trim().slice(0, 200), {
                    title: this.displayName, sticky: true,
                    buttons: [{ name: _t("Open conversation"), onClick: () => this.open({ focus: true }) }],
                }));
        }
    },
    open() { dismissReply(this); return super.open(...arguments); },
    setAsDiscussThread() { dismissReply(this); return super.setAsDiscussThread(...arguments); },
    setup() { super.setup(...arguments); this.is_odupilot = false; this.odupilot_session = null; this.odupilot_stream = null; },
    _computeDiscussAppCategory() { return this.is_odupilot ? this.store.discuss.odupilot : super._computeDiscussAppCategory(); },
    openChatWindow(options) {
        if (this.odupilot_session?.discuss_only) { return this.store.env.services.action.doAction({ type: "ir.actions.client", tag: "mail.action_discuss", context: { active_id: this.id } }); }
        return super.openChatWindow(...arguments);
    },
});
patch(Message.prototype, {
    get isNotification() { return !this.odupilot_assistant && super.isNotification; },
    setup() {
        super.setup(...arguments);
        this.odupilot_permission = null; this.odupilot_recovery = null;
        this.odupilot_assistant = false; this.odupilot_step = false;
    },
});
