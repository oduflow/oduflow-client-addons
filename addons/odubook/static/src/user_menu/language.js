/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Выбор языка интерфейса: список установленных языков базы.
 *
 * Книга переключается кнопками над документом и язык профиля не трогает; этот
 * диалог, наоборот, меняет язык всего Odoo, поэтому живёт в меню пользователя,
 * а не внутри книги.
 */
export class LanguageDialog extends Component {
    setup() {
        this.title = _t("Language");
        this.rpc = useService("rpc");
        this.orm = useService("orm");
        this.user = useService("user");
        this.state = useState({
            languages: [],
            current: null,
            // Пока язык переписывается и страница перезагружается, повторный
            // щелчок ничего менять не должен.
            switching: false,
        });

        onWillStart(async () => {
            const data = await this.rpc("/odubook/languages", {});
            this.state.languages = data.languages || [];
            this.state.current = data.current || null;
        });
    }

    async selectLanguage(code) {
        if (this.state.switching) {
            return;
        }
        if (code === this.state.current) {
            this.props.close();
            return;
        }
        this.state.switching = true;
        // Язык -- поле, которое пользователь вправе писать себе сам.
        await this.orm.write("res.users", [this.user.userId], { lang: code });
        // Клиент уже собран на прежнем языке: переводы приезжают с новой
        // загрузкой страницы, а не с перерисовкой компонента.
        browser.location.reload();
    }
}

LanguageDialog.template = "odubook.LanguageDialog";
LanguageDialog.components = { Dialog };
LanguageDialog.props = { close: Function };

/**
 * Пункт меню пользователя: открывает выбор языка интерфейса.
 */
function languageItem(env) {
    return {
        type: "item",
        id: "odubook_language",
        description: _t("Language"),
        callback: () => {
            env.services.dialog.add(LanguageDialog);
        },
        // Между «Shortcuts» и разделителем перед настройками профиля.
        sequence: 35,
    };
}

registry.category("user_menuitems").add("odubook_language", languageItem);
