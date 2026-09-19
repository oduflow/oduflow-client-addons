/** @odoo-module **/
import { registerPatch } from "@mail/model/model_core";
import { attr, one } from "@mail/model/model_field";

for (const [name, keys] of [
    ["Thread", ["is_odupilot", "odupilot_session", "odupilot_stream"]],
    ["Message", ["odupilot_permission", "odupilot_recovery", "odupilot_assistant", "odupilot_step"]],
]) {
    registerPatch({ name, fields: Object.fromEntries(keys.map(key => [key, attr()])),
        modelMethods: { convertData(data) {
            const result = this._super(data);
            for (const key of keys) { if (key in data) { result[key] = data[key]; } }
            return result;
        } },
    });
}
registerPatch({ name: "Discuss", fields: {
    categoryAI: one("DiscussSidebarCategory", { inverse: "discussAsAI", default: {} }),
} });
registerPatch({ name: "DiscussSidebarCategory", fields: {
    discussAsAI: one("Discuss", { identifying: true, inverse: "categoryAI" }),
    name: { compute() { return this.discussAsAI ? this.env._t("OduPilot") : this._super(); } },
    supportedChannelTypes: { compute() { return this.discussAsAI ? ["channel", "chat", "group"] : this._super(); } },
    orderedCategoryItems: { compute() { return this.discussAsAI ? this.categoryItems : this._super(); } },
    serverStateKey: { compute() { return this.discussAsAI ? "is_discuss_sidebar_category_ai_open" : this._super(); } },
    isServerOpen: { compute() { return this.discussAsAI ? true : this._super(); } },
} });
registerPatch({ name: "Channel", fields: {
    discussSidebarCategory: { compute() {
        return this.thread?.is_odupilot ? this.messaging.discuss.categoryAI : this._super();
    } },
} });
