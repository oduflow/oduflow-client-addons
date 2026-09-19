/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

import { Component, onWillStart, onMounted, onPatched, useState, useRef, markup } from "@odoo/owl";

//: Заголовки, у которых появляются кнопки: глубже третьего уровня раздел уже
//: слишком мелок, чтобы выгружать его отдельным документом.
const HEADING_TAGS = "h1, h2, h3";
//: Набор глав собирают по многу заходов, поэтому он переживает перезагрузку
//: страницы: ключ хранилища свой у пользовательской книги и у книги админа.
const SELECTION_KEY = "odubook.selection";
const TOOL_HEADINGS = "h1[id], h2[id], h3[id]";

/**
 * Клиентское действие «Книга»: список модулей слева и документ справа.
 *
 * По умолчанию книга открывается на языке профиля читателя, а кнопки над
 * документом переключают её на любой язык, на котором документация вообще
 * ведётся: перевод бывает точнее исходника, а исходник -- свежее перевода.
 */
export class BookApp extends Component {
    setup() {
        this.root = useRef("root");
        this.rpc = useService("rpc");
        this.markup = markup;
        this.notification = useService("notification");
        // Ссылка, по которой книгу открыли: страница, раздел и язык.
        this.link = this._linkParams();
        this.state = useState({
            pages: [],
            // Языки, на которых документ есть хотя бы у одного модуля.
            languages: [],
            // Язык показа: сервер решает его при первой загрузке.
            lang: null,
            activeId: null,
            search: "",
            loaded: false,
            // Отмеченные галочками разделы: набор живёт поверх страниц, чтобы
            // в один PDF попадали главы разных руководств.
            selection: this._restoreSelection(),
        });

        onWillStart(async () => {
            await this._loadBook(this.link.lang);
            if (this.link.page && this.state.pages.some((page) => page.id === this.link.page)) {
                this.state.activeId = this.link.page;
            }
            this.state.loaded = true;
        });
        // Текст документа приходит готовым HTML, поэтому кнопки к его
        // заголовкам дописываются после отрисовки, а не в шаблоне.
        onMounted(() => this._afterRender());
        onPatched(() => this._afterRender());
    }

    /**
     * Разобрать параметры ссылки на книгу. Значения приходят из адресной
     * строки, поэтому проверяются здесь, а не там, где применяются.
     */
    _linkParams() {
        const params = { ...this.env.services.router.current.hash, ...this.props.action?.params };
        return {
            page: params.page ? String(params.page) : null,
            section: params.section ? String(params.section) : null,
            lang: params.book_lang ? String(params.book_lang) : undefined,
        };
    }

    _afterRender() {
        this._injectHeadingTools();
        this._syncSelection();
        this._syncLinkScroll();
    }

    /** Дописать к каждому заголовку документа кнопки экспорта и ссылки. */
    _injectHeadingTools() {
        const doc = this.root.el && this.root.el.querySelector(".o_odubook_doc");
        if (!doc) {
            return;
        }
        for (const heading of doc.querySelectorAll(TOOL_HEADINGS)) {
            if (heading.querySelector(".o_odubook_tools")) {
                continue;
            }
            const tools = document.createElement("span");
            tools.className = "o_odubook_tools";
            tools.appendChild(
                this._pickBox(_t("Add this section to the PDF selection"))
            );
            tools.appendChild(
                this._toolButton("pdf", "fa-file-pdf-o", _t("Download this section as PDF"))
            );
            tools.appendChild(
                this._toolButton("link", "fa-link", _t("Copy a link to this heading"))
            );
            heading.appendChild(tools);
        }
    }

    _selectionKey() {
        return `${SELECTION_KEY}.${this.constructor.book}`;
    }

    /** Прочитать набор из хранилища браузера; битое значение -- пустой набор. */
    _restoreSelection() {
        let stored = null;
        try {
            stored = JSON.parse(browser.localStorage.getItem(this._selectionKey()));
        } catch (error) {
            return [];
        }
        if (!Array.isArray(stored)) {
            return [];
        }
        return stored
            .filter((picked) => picked && picked.module && picked.section)
            .map((picked) => ({
                module: String(picked.module),
                section: String(picked.section),
            }));
    }

    /**
     * Запомнить набор. Хранилище бывает недоступно -- приватный режим,
     * переполнение, -- и это не повод ронять книгу: набор просто доживёт до
     * перезагрузки.
     */
    _saveSelection() {
        try {
            browser.localStorage.setItem(
                this._selectionKey(),
                JSON.stringify(this.state.selection)
            );
        } catch (error) {
            // Хранить негде: набор остаётся только в памяти вкладки.
        }
    }

    /** Галочка «взять в набор»: из отмеченных разделов собирается один PDF. */
    _pickBox(label) {
        const box = document.createElement("input");
        box.type = "checkbox";
        box.className = "o_odubook_pick";
        box.title = label;
        box.setAttribute("aria-label", label);
        return box;
    }

    /** Расставить галочки по набору: страница и язык меняются, набор -- нет. */
    _syncSelection() {
        const doc = this.root.el && this.root.el.querySelector(".o_odubook_doc");
        if (!doc) {
            return;
        }
        for (const box of doc.querySelectorAll(".o_odubook_pick")) {
            const heading = box.closest(HEADING_TAGS);
            const picked = this._pickIndex(heading && heading.id) !== -1;
            box.checked = picked;
            const tools = box.closest(".o_odubook_tools");
            if (tools) {
                tools.classList.toggle("o_picked", picked);
            }
        }
    }

    /** Место раздела в наборе или ``-1``: раздел опознаётся страницей и якорем. */
    _pickIndex(section) {
        if (!section) {
            return -1;
        }
        return this.state.selection.findIndex(
            (picked) => picked.module === this.state.activeId && picked.section === section
        );
    }

    /** Добавить раздел в набор или убрать его оттуда. */
    togglePick(section) {
        if (!section || !this.state.activeId) {
            return;
        }
        const index = this._pickIndex(section);
        if (index === -1) {
            this.state.selection.push({ module: this.state.activeId, section });
        } else {
            this.state.selection.splice(index, 1);
        }
        this._saveSelection();
    }

    clearSelection() {
        this.state.selection = [];
        this._saveSelection();
    }

    /** Скачать отмеченные разделы одним PDF, в порядке отметки. */
    exportSelection() {
        if (!this.state.selection.length) {
            return;
        }
        const query = new URLSearchParams({
            sections: this.state.selection
                .map((picked) => `${picked.module}|${picked.section}`)
                .join(","),
            book: this.constructor.book,
        });
        if (this.state.lang) {
            query.set("lang", this.state.lang);
        }
        browser.open(`/odubook/guide/pdf/bundle?${query.toString()}`, "_blank");
    }

    _toolButton(action, icon, label) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-sm o_odubook_tool";
        button.dataset.action = action;
        button.title = label;
        button.setAttribute("aria-label", label);
        const glyph = document.createElement("i");
        glyph.className = `fa ${icon}`;
        button.appendChild(glyph);
        return button;
    }

    /** Клик по документу: интересны только дописанные кнопки заголовков. */
    onDocClick(ev) {
        if (!ev.target.closest) {
            return;
        }
        const box = ev.target.closest(".o_odubook_pick");
        if (box) {
            const picked = box.closest(HEADING_TAGS);
            this.togglePick(picked ? picked.id : null);
            return;
        }
        const button = ev.target.closest(".o_odubook_tool");
        if (!button) {
            return;
        }
        const heading = button.closest(HEADING_TAGS);
        const section = heading ? heading.id : null;
        if (button.dataset.action === "pdf") {
            this.exportPdf(section);
        } else {
            this.copyLink(section);
        }
    }

    /** Скачать раздел под заголовком одним PDF. */
    exportPdf(section) {
        if (!this.state.activeId) {
            return;
        }
        const query = new URLSearchParams({
            module: this.state.activeId,
            book: this.constructor.book,
        });
        if (section) {
            query.set("section", section);
        }
        if (this.state.lang) {
            query.set("lang", this.state.lang);
        }
        browser.open(`/odubook/guide/pdf?${query.toString()}`, "_blank");
    }

    /**
     * Положить в буфер обмена ссылку на этот заголовок. Буфер обмена доступен
     * не везде -- по HTTP его нет вовсе, -- поэтому при отказе показываем сам
     * адрес: его читатель скопирует руками.
     */
    async copyLink(section) {
        const hash = new URLSearchParams({
            action: this.constructor.action,
            page: this.state.activeId || "",
        });
        if (section) {
            hash.set("section", section);
        }
        if (this.state.lang) {
            hash.set("book_lang", this.state.lang);
        }
        const url = `${browser.location.origin}/odoo/action-${hash.get("action")}?${new URLSearchParams([...hash].filter(([key]) => key !== "action")).toString()}`;
        try {
            await browser.navigator.clipboard.writeText(url);
        } catch (error) {
            this.notification.add(url, { title: _t("Copy this link"), sticky: true });
            return;
        }
        this.notification.add(_t("Link copied to the clipboard"), { type: "success" });
    }

    /**
     * Ссылка на заголовок ведёт к нему самому, а не к началу страницы: после
     * первой отрисовки прокручиваем документ к разделу, и только один раз.
     */
    _syncLinkScroll() {
        if (!this.link.section || !this.root.el) {
            return;
        }
        const target = this.root.el.querySelector(
            `.o_odubook_doc [id="${CSS.escape(this.link.section)}"]`
        );
        if (!target) {
            return;
        }
        this.link.section = null;
        target.scrollIntoView({ block: "start" });
    }

    /** Перечитать книгу целиком: язык меняет текст каждой страницы. */
    async _loadBook(lang) {
        const data = await this.rpc(this.constructor.endpoint, {
            lang: lang || undefined,
        });
        this.state.pages = data.pages || [];
        this.state.languages = data.languages || [];
        this.state.lang = data.lang || null;
        // Набор страниц от языка не зависит -- открытый модуль остаётся
        // открытым, но модуль мог и уехать из книги между загрузками.
        const stillThere = this.state.pages.some((page) => page.id === this.state.activeId);
        if (!stillThere) {
            this.state.activeId = this.state.pages.length ? this.state.pages[0].id : null;
        }
    }

    /** Кнопки языков: короткий код на кнопке, название языка в подсказке. */
    get languages() {
        return this.state.languages.map((language) => ({
            code: language.code,
            label: language.code.toUpperCase(),
            name: language.name,
            active: language.code === this.state.lang,
        }));
    }

    async selectLanguage(code) {
        if (code === this.state.lang) {
            return;
        }
        await this._loadBook(code);
    }

    get filteredPages() {
        const query = this.state.search.trim().toLowerCase();
        if (!query) {
            return this.state.pages;
        }
        return this.state.pages.filter((page) =>
            page.title.toLowerCase().includes(query)
        );
    }

    get activePage() {
        return this.state.pages.find((page) => page.id === this.state.activeId) || null;
    }

    selectPage(id) {
        this.state.activeId = id;
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
    }
}

BookApp.props = ["*"];
BookApp.template = "odubook.BookApp";
// JSON endpoint, тег действия и вид книги переопределяются в AdminBookApp;
// остальная логика общая.
BookApp.endpoint = "/odubook/book";
BookApp.action = "odubook.book";
BookApp.book = "user";

registry.category("actions").add("odubook.book", BookApp);
