/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";


function jsonValue(value, fallback) {
    try {
        return JSON.parse(JSON.stringify(value));
    } catch (_error) {
        return fallback;
    }
}

function currentDeveloperContext(env) {
    const controller = env.services.action.currentController || {};
    const action = controller.action || {};
    const router = env.services.router.current || {};
    const hash = router.hash || {};
    const props = controller.props || {};
    const viewType = hash.view_type || (controller.view && controller.view.type) || "";
    let viewId = hash.view_id || "";
    if (!viewId && action.views && viewType) {
        const view = action.views.find((item) => item[1] === viewType && item[0]);
        viewId = view ? view[0] : "";
    }
    const actionContext = action.context || {};
    const resId = hash.resId || props.resId || actionContext.active_id || false;
    const resIds = props.resIds || actionContext.active_ids || (resId ? [resId] : []);
    return {
        url: window.location.href,
        document_title: document.title,
        router: jsonValue(hash, {}),
        action: {
            id: action.id || hash.action || false,
            name: action.display_name || action.name || "",
            type: action.type || "",
            res_model: action.res_model || props.resModel || hash.model || "",
            context: jsonValue(actionContext, {}),
            domain: jsonValue(action.domain || props.domain || [], []),
            views: jsonValue(action.views || [], []),
            target: action.target || "",
        },
        controller: {
            view_type: viewType,
            view_id: viewId || false,
            res_model: props.resModel || action.res_model || hash.model || "",
            res_id: resId,
            res_ids: jsonValue(resIds, []),
        },
    };
}

function aiDeveloperItem({ env }) {
    if (!env.services.user.isAdmin) {
        return null;
    }
    return {
        type: "item",
        description: _t("AI Developer"),
        callback: () => env.services.action.doAction(
            "odupilot.action_odupilot_developer_wizard",
            {
                additionalContext: {
                    default_source_context_json: JSON.stringify(
                        currentDeveloperContext(env)
                    ),
                },
            }
        ),
        sequence: 95,
    };
}

registry.category("debug").category("default").add(
    "odupilot.ai_developer",
    aiDeveloperItem
);
