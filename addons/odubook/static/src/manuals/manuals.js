/** @odoo-module **/

import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { sprintf } from "@web/core/utils/strings";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

import { Component, onWillStart, useRef, useState, markup } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

//: Полка рассчитана на документы; предел совпадает с серверным.
const MAX_MANUAL_BYTES = 25 * 1024 * 1024;

/**
 * Клиентское действие «Manuals»: полка вручную вложенных документов.
 *
 * Слева -- список документов и загрузка для администратора, справа -- сам
 * документ. Markdown и текст приходят с сервера готовым HTML, HTML-артефакт и
 * PDF показываются во фрейме, картинка -- изображением, остальное предлагается
 * скачать.
 *
 * У документа может быть несколько языковых версий. По умолчанию читатель
 * видит версию своего языка Odoo, а переключателем над документом выбирает
 * другую; администратор тем же переключателем догружает недостающий перевод.
 */
export class ManualsApp extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.markup = markup;
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.user = useService("user");
        this.fileInput = useRef("fileInput");
        // Язык и документ выбранного файла решаются до диалога выбора: в
        // обработчике change остаётся только прочитать байты.
        this._pendingLang = null;
        this._pendingManualId = null;
        this.state = useState({
            manuals: [],
            languages: [],
            canEdit: false,
            activeId: null,
            search: "",
            loaded: false,
            // Отрендеренный текст версий: ключ -- "<id документа>|<язык>".
            html: {},
            // Язык, выбранный читателем вручную; пусто -- язык его профиля.
            lang: null,
            // Выбранный, но ещё не загруженный файл: заголовок и язык правятся
            // до отправки, потому что имя файла редко годится в заголовки.
            pending: null,
            uploading: false,
        });

        onWillStart(async () => {
            await this._reloadShelf();
            this.state.loaded = true;
        });
    }

    get filteredManuals() {
        const query = this.state.search.trim().toLowerCase();
        if (!query) {
            return this.state.manuals;
        }
        return this.state.manuals.filter(
            (manual) =>
                manual.name.toLowerCase().includes(query) ||
                (manual.file_name || "").toLowerCase().includes(query)
        );
    }

    get activeManual() {
        return this.state.manuals.find((manual) => manual.id === this.state.activeId) || null;
    }

    /** Языки открытого документа с пометкой, какой из них показан. */
    get activeLanguages() {
        const manual = this.activeManual;
        if (!manual) {
            return [];
        }
        const known = new Map(this.state.languages.map((language) => [language.code, language.name]));
        const codes = new Set(manual.langs);
        // Язык без версии показываем только администратору: ему по этой кнопке
        // и догружать перевод, читателю пустая кнопка ни к чему.
        if (this.state.canEdit) {
            for (const language of this.state.languages) {
                codes.add(language.code);
            }
        }
        return [...codes].sort().map((code) => ({
            code,
            label: code.toUpperCase(),
            name: known.get(code) || code,
            active: code === manual.lang,
            missing: !manual.langs.includes(code),
        }));
    }

    /** Текст открытой версии ждём с сервера: пока его нет -- «загружается». */
    get activeTextLoading() {
        const manual = this.activeManual;
        if (!manual || (manual.kind !== "markdown" && manual.kind !== "text")) {
            return false;
        }
        return !(this._htmlKey(manual) in this.state.html);
    }

    /** Отрендеренный текст открытой версии, если он у нас есть. */
    get activeHtml() {
        const manual = this.activeManual;
        return (manual && this.state.html[this._htmlKey(manual)]) || "";
    }

    _htmlKey(manual) {
        return `${manual.id}|${manual.lang}`;
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
    }

    async selectManual(id) {
        this.state.activeId = id;
        await this._loadText();
    }

    /**
     * Показать документы на выбранном языке. Индекс перезапрашивается целиком:
     * язык меняет и ссылку на содержимое, и формат каждой карточки.
     */
    async selectLanguage(language) {
        if (language.missing) {
            this.addTranslation(language.code);
            return;
        }
        if (this.state.lang === language.code) {
            return;
        }
        this.state.lang = language.code;
        await this._reloadShelf(this.state.activeId);
    }

    /** Перечитать индекс полки на текущем языке и подтянуть текст. */
    async _reloadShelf(keepId) {
        const data = await this.rpc("/odubook/manuals", {
            lang: this.state.lang || undefined,
        });
        this._applyShelf(data, keepId);
        await this._loadText();
    }

    /** Подтянуть текст открытой версии, если модуль рендерит её сам. */
    async _loadText() {
        const manual = this.activeManual;
        // Байты HTML, PDF и картинок браузер берёт сам по ссылке; с сервера
        // запрашивается только то, что он рендерит для нас.
        if (!manual || (manual.kind !== "markdown" && manual.kind !== "text")) {
            return;
        }
        const key = this._htmlKey(manual);
        if (key in this.state.html) {
            return;
        }
        const data = await this.rpc("/odubook/manuals/read", {
            manual_id: manual.id,
            lang: this.state.lang || undefined,
        });
        this.state.html[key] = data.html || "";
    }

    openFilePicker() {
        this._pendingLang = null;
        this._pendingManualId = null;
        if (this.fileInput.el) {
            this.fileInput.el.click();
        }
    }

    /** Догрузить недостающий перевод открытого документа. */
    addTranslation(lang) {
        const manual = this.activeManual;
        if (!manual || !this.state.canEdit) {
            return;
        }
        this._pendingLang = lang || null;
        this._pendingManualId = manual.id;
        if (this.fileInput.el) {
            this.fileInput.el.click();
        }
    }

    /** Прочитать выбранный файл и предложить заголовок до отправки. */
    async onFileSelected(ev) {
        const file = ev.target.files && ev.target.files[0];
        // Тот же файл, выбранный повторно, должен снова поднимать change.
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (file.size > MAX_MANUAL_BYTES) {
            this.notification.add(_t("This file is too large to be added to the shelf."), {
                type: "danger",
            });
            return;
        }
        const data = await this._readAsBase64(file);
        const manual = this._pendingManualId
            ? this.state.manuals.find((item) => item.id === this._pendingManualId)
            : null;
        this.state.pending = {
            name: manual ? manual.name : file.name.replace(/\.[^.]+$/, ""),
            fileName: file.name,
            lang: this._pendingLang || this._defaultLang(),
            manualId: this._pendingManualId || null,
            data,
        };
    }

    /** Язык по умолчанию для новой версии: язык профиля загружающего. */
    _defaultLang() {
        const code = String(this.user.context.lang || "en").split("_")[0];
        const known = this.state.languages.some((language) => language.code === code);
        return known ? code : (this.state.languages[0] || { code: "en" }).code;
    }

    onPendingNameInput(ev) {
        if (this.state.pending) {
            this.state.pending.name = ev.target.value;
        }
    }

    onPendingLangChange(ev) {
        if (this.state.pending) {
            this.state.pending.lang = ev.target.value;
        }
    }

    cancelUpload() {
        this.state.pending = null;
    }

    async confirmUpload() {
        const pending = this.state.pending;
        if (!pending || this.state.uploading) {
            return;
        }
        this.state.uploading = true;
        try {
            const known = new Set(this.state.manuals.map((manual) => manual.id));
            const data = await this.rpc("/odubook/manuals/upload", {
                name: pending.name,
                file_name: pending.fileName,
                data: pending.data,
                lang: pending.lang,
                manual_id: pending.manualId || undefined,
            });
            const added = (data.manuals || []).find((manual) => !known.has(manual.id));
            // Вложенную версию читатель должен увидеть сразу, поэтому полка
            // переключается на её язык.
            this.state.lang = pending.lang;
            await this._reloadShelf(added ? added.id : pending.manualId || this.state.activeId);
            this.state.pending = null;
        } finally {
            this.state.uploading = false;
        }
    }

    askRemove(manual) {
        const single = manual.langs.length < 2;
        this.dialog.add(ConfirmationDialog, {
            title: single ? _t("Remove document") : _t("Remove translation"),
            body: single
                ? sprintf(_t("Remove “%s” from the shelf?"), manual.name)
                : sprintf(
                      _t("Remove the %s version of “%s”?"),
                      String(manual.lang).toUpperCase(),
                      manual.name
                  ),
            confirm: () => this.removeManual(manual.id, single ? null : manual.lang),
            // Без обработчика отмены диалог показывает одну кнопку OK.
            cancel: () => {},
        });
    }

    async removeManual(id, lang) {
        await this.rpc("/odubook/manuals/delete", {
            manual_id: id,
            lang: lang || undefined,
        });
        for (const key of Object.keys(this.state.html)) {
            if (key.startsWith(`${id}|`)) {
                delete this.state.html[key];
            }
        }
        await this._reloadShelf(id);
    }

    /** Принять индекс полки с сервера, сохранив разумный выбор документа. */
    _applyShelf(data, keepId) {
        this.state.manuals = (data && data.manuals) || [];
        this.state.languages = (data && data.languages) || [];
        this.state.canEdit = Boolean(data && data.can_edit);
        const wanted = keepId || this.state.activeId;
        const stillThere = this.state.manuals.some((manual) => manual.id === wanted);
        if (stillThere) {
            this.state.activeId = wanted;
        } else {
            this.state.activeId = this.state.manuals.length ? this.state.manuals[0].id : null;
        }
    }

    /** Содержимое файла в base64 без префикса data-URL. */
    _readAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }
}

ManualsApp.props = { ...standardActionServiceProps };
ManualsApp.template = "odubook.ManualsApp";

registry.category("actions").add("odubook.manuals", ManualsApp);
