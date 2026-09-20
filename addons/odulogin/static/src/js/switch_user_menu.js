/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

import { Component, useState } from "@odoo/owl";


export class OduLoginSystray extends Component {
    static template = "odulogin.OduLoginSystray";
    static props = {};

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({ busy: false });
        this.session = session;
    }

    openSwitchWizard() {
        return this.action.doAction("odulogin.action_odulogin_switch_wizard");
    }

    async switchBack() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("odulogin.session", "switch_back", []);
            browser.location.reload();
        } finally {
            this.state.busy = false;
        }
    }

    get switchBackTitle() {
        return this.session.odulogin_origin_name
            ? _t("Return to %s", this.session.odulogin_origin_name)
            : _t("Return to administrator");
    }
}

registry.category("systray").add(
    "odulogin.switch_user",
    {
        Component: OduLoginSystray,
        isDisplayed: () => session.odulogin_can_switch || session.odulogin_is_switched,
    },
    { sequence: 2 }
);
