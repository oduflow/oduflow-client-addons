/** @odoo-module **/
import { Thread } from "@mail/core/common/thread_model";
import { Message } from "@mail/core/common/message_model";
import { discussSidebarCategoriesRegistry } from "@mail/discuss/core/web/discuss_sidebar_categories";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

function aiCategory(store) {
    return store.DiscussAppCategory.get("odupilot") || store.DiscussAppCategory.insert({
        id: "odupilot", name: _t("OduPilot"), isOpen: true, canView: false,
        canAdd: false, serverStateKey: "is_discuss_sidebar_category_ai_open",
    });
}
discussSidebarCategoriesRegistry.add("odupilot", { value: aiCategory }, { sequence: 20 });
patch(Thread.prototype, {
    update(data) {
        super.update(...arguments);
        for (const key of ["is_odupilot", "odupilot_session", "odupilot_stream"]) {
            if (key in data) { this[key] = data[key]; }
        }
        if (this.is_odupilot) {
            this._store.discuss.channels.threads.delete(this);
            this._store.discuss.chats.threads.delete(this);
            aiCategory(this._store).threads.add(this);
        }
    },
});
patch(Message.prototype, {
    update(data) {
        super.update(...arguments);
        for (const key of ["odupilot_permission", "odupilot_recovery", "odupilot_assistant", "odupilot_step"]) {
            if (key in data) { this[key] = data[key]; }
        }
    },
});
