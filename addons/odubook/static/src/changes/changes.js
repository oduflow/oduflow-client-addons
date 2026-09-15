/** @odoo-module **/

import { router } from "@web/core/browser/router";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { sprintf } from "@web/core/utils/strings";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

import { Component, onWillStart, onMounted, onPatched, onWillUnmount, useState, useRef, markup } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
const { DateTime } = luxon;

/** Ключ записи летописи: пара «модуль + дата». */
function entryKey(entry) {
    return `${entry.module}|${entry.date}`;
}

//: Режимы группировки, которые принимаются из ссылки: чужой параметр не должен
//: увести архив в несуществующий режим.
const GROUP_MODES = ["date", "module", "module_date"];

//: Набор записей собирают по многу заходов -- переходя между месяцами,
//: модулями и языками, -- поэтому он переживает перезагрузку страницы.
const SELECTION_KEY = "odubook.changes.selection";

//: Геометрия графика месяцев. Значения в пикселях, SVG рисуется один к одному:
//: столбцы одинаковой ширины, а лишние месяцы уходят в горизонтальную прокрутку.
const CHART_BAR_W = 22;
const CHART_BAR_STEP = 32;
const CHART_PLOT_H = 72;
//: Место над столбцами под подпись значения.
const CHART_TOP = 14;
//: Место под осью: месяц и, при смене года, год.
const CHART_AXIS_H = 24;
//: Месяц с одной записью тоже должен быть виден.
const CHART_MIN_BAR = 3;
//: Зазор фона между прочитанным и непрочитанным сегментами столбца.
const CHART_SEGMENT_GAP = 2;

/** Столбец со скруглённым верхом, стоящий на оси. */
function barPath(x, y, width, height) {
    const r = Math.min(4, width / 2, height);
    return (
        `M${x},${y + height}V${y + r}A${r},${r} 0 0 1 ${x + r},${y}` +
        `H${x + width - r}A${r},${r} 0 0 1 ${x + width},${y + r}V${y + height}Z`
    );
}

/**
 * Летопись изменений: слева месяцы, дни или модули, справа записи выбранной
 * группы. Прочитанной считается запись, которую читатель действительно увидел.
 *
 * Три режима:
 *   date        -- лента месяца: изменения подряд, позднейшее сверху;
 *   module_date -- день целиком: записи всех модулей за выбранную дату;
 *   module      -- все записи одного модуля.
 */
export class ChangesApp extends Component {
    setup() {
        this.root = useRef("root");
        this.rpc = rpc;
        this.markup = markup;
        this.notification = useService("notification");
        // Ссылка, по которой архив открыли: режим, группа и запись в ней.
        this.link = this._linkParams();
        // Записи открытой группы: подсветку с них снимаем при уходе с группы.
        this._highlighted = [];
        // Ключи записей, уже отмеченных прочитанными на сервере.
        this._seen = new Set();
        // В ленте месяца прочитанным считается доскроллленное, а не загруженное.
        this._observer = null;
        this._observed = new Set();
        this.state = useState({
            entries: [],
            // Языки, на которых летопись ведётся хотя бы у одного модуля.
            languages: [],
            // Язык записей: сервер решает его при первой загрузке.
            lang: null,
            groupBy: "date",
            activeKey: null,
            html: {},
            loaded: false,
            // График месяцев по умолчанию свёрнут: прилипший блок отнимает
            // высоту у текста, кому нужен -- включает кнопкой Chart.
            showChart: false,
            // Отмеченные галочками записи: набор живёт поверх групп, чтобы в
            // один PDF попадали изменения разных модулей и месяцев.
            selection: this._restoreSelection(),
        });

        if (this.link.groupBy) {
            this.state.groupBy = this.link.groupBy;
        }

        onWillStart(async () => {
            const data = await this.rpc("/odubook/changes", { lang: this.link.lang });
            this.state.entries = data.entries || [];
            this.state.languages = data.languages || [];
            this.state.lang = data.lang || null;
            this.state.loaded = true;
            const key = this._startGroupKey();
            if (key) {
                await this.selectGroup(key);
            }
        });
        onMounted(() => {
            this._syncObserver();
            this._syncChartScroll();
            this._syncLinkScroll();
        });
        onPatched(() => {
            this._syncObserver();
            this._syncChartScroll();
            this._syncLinkScroll();
        });
        onWillUnmount(() => this._stopObserver());
    }

    /** Лента: слева месяцы, справа изменения месяца в хронологии. */
    get groupedByFeed() {
        return this.state.groupBy === "date";
    }

    /** День: слева даты по месяцам, справа записи модулей за день. */
    get groupedByDate() {
        return this.state.groupBy === "module_date";
    }

    get groupedByModule() {
        return this.state.groupBy === "module";
    }

    /** Заголовок записи справа несёт модуль в обоих датовых режимах. */
    get entryHeadIsModule() {
        return this.groupedByFeed || this.groupedByDate;
    }

    /**
     * Левая колонка: секции (месяцы или один общий блок) со списком групп.
     * Группа -- месяц в ленте, день в режиме дат и модуль в режиме модулей.
     */
    get archive() {
        if (this.groupedByFeed) {
            return this._archiveByMonth();
        }
        return this.groupedByDate ? this._archiveByDate() : this._archiveByModule();
    }

    /** Ключ группы, к которой относится запись в текущем режиме. */
    _groupKey(entry) {
        if (this.groupedByFeed) {
            return entry.date.slice(0, 7);
        }
        return this.groupedByDate ? entry.date : entry.module;
    }

    _archiveByMonth() {
        const months = new Map();
        for (const entry of this.state.entries) {
            const key = entry.date.slice(0, 7);
            let month = months.get(key);
            if (!month) {
                month = { key, label: this.formatMonth(key), count: 0, unread: 0 };
                months.set(key, month);
            }
            month.count++;
            if (entry.unread) {
                month.unread++;
            }
        }
        // Записи приходят в порядке публикации, а месяцы слева нужны
        // календарные: свежий сверху.
        const items = [...months.values()].sort((a, b) => b.key.localeCompare(a.key));
        return items.length ? [{ key: "months", label: false, items }] : [];
    }

    /**
     * График ленты: по оси абсцисс месяцы в хронологии, по оси ординат число
     * изменений месяца. Столбец делится на прочитанное и непрочитанное, чтобы
     * читатель видел не только объём месяца, но и свой долг по нему.
     *
     * Возвращает ``false``, когда рисовать нечего: график живёт только в ленте
     * и осмыслен от двух месяцев.
     */
    get monthChart() {
        if (!this.groupedByFeed || !this.state.showChart) {
            return false;
        }
        const sections = this._archiveByMonth();
        // Слева в списке свежий месяц сверху, на графике -- время слева направо.
        const months = sections.length ? [...sections[0].items].reverse() : [];
        if (months.length < 2) {
            return false;
        }
        const max = Math.max(...months.map((month) => month.count));
        const base = CHART_TOP + CHART_PLOT_H;
        let year = null;
        const bars = months.map((month, index) => {
            const x = index * CHART_BAR_STEP + (CHART_BAR_STEP - CHART_BAR_W) / 2;
            const height = Math.max(
                CHART_MIN_BAR,
                Math.round((CHART_PLOT_H * month.count) / max)
            );
            // Непрочитанное занимает свою долю столбца сверху; когда прочитанного
            // не остаётся, зазор и нижний сегмент не рисуются вовсе.
            let unreadHeight = 0;
            if (month.unread) {
                unreadHeight =
                    month.unread === month.count
                        ? height
                        : Math.min(
                              height - CHART_MIN_BAR - CHART_SEGMENT_GAP,
                              Math.max(
                                  CHART_MIN_BAR,
                                  Math.round((height * month.unread) / month.count)
                              )
                          );
                unreadHeight = Math.max(unreadHeight, CHART_MIN_BAR);
            }
            const readHeight = unreadHeight
                ? height - unreadHeight - CHART_SEGMENT_GAP
                : height;
            const topHeight = unreadHeight || height;
            const monthYear = month.key.slice(0, 4);
            const showYear = monthYear !== year;
            year = monthYear;
            return {
                key: month.key,
                label: this.formatMonthShort(month.key),
                year: showYear ? monthYear : false,
                count: month.count,
                unread: month.unread,
                active: month.key === this.state.activeKey,
                // Подпись значения висит только над выбранным и над самым
                // высоким столбцом: остальные показывают её при наведении.
                peak: month.count === max,
                // Столбец целиком отдан под наведение и клик, а не только его
                // видимая часть: у редкого месяца она в три пикселя высотой.
                hitY: CHART_TOP,
                hitH: CHART_PLOT_H,
                x,
                w: CHART_BAR_W,
                centerX: x + CHART_BAR_W / 2,
                top: barPath(x, base - height, CHART_BAR_W, topHeight),
                bottomY: base - readHeight,
                bottomH: unreadHeight ? readHeight : 0,
                valueY: base - height - 4,
                labelY: base + 13,
                yearY: base + 22,
                title: month.unread
                    ? `${this.formatMonth(month.key)}: ${month.count} changes, ${
                          month.unread
                      } unread`
                    : `${this.formatMonth(month.key)}: ${month.count} changes`,
            };
        });
        return {
            bars,
            max,
            width: months.length * CHART_BAR_STEP,
            height: base + CHART_AXIS_H,
            axisY: base + 0.5,
            hasUnread: bars.some((bar) => bar.unread),
        };
    }

    _archiveByDate() {
        const days = new Map();
        for (const entry of this.state.entries) {
            let day = days.get(entry.date);
            if (!day) {
                day = {
                    key: entry.date,
                    label: this.formatDayShort(entry.date),
                    count: 0,
                    unread: 0,
                };
                days.set(entry.date, day);
            }
            day.count++;
            if (entry.unread) {
                day.unread++;
            }
        }
        // Дни календарные, а не в порядке публикации: свежий день сверху, и
        // месяц каждой записи в списке ровно один.
        const sections = [];
        for (const day of [...days.values()].sort((a, b) => b.key.localeCompare(a.key))) {
            const monthKey = day.key.slice(0, 7);
            let section = sections[sections.length - 1];
            if (!section || section.key !== monthKey) {
                section = { key: monthKey, label: this.formatMonth(monthKey), items: [] };
                sections.push(section);
            }
            section.items.push(day);
        }
        return sections;
    }

    _archiveByModule() {
        const modules = new Map();
        for (const entry of this.state.entries) {
            let module = modules.get(entry.module);
            if (!module) {
                module = { key: entry.module, label: entry.title, count: 0, unread: 0 };
                modules.set(entry.module, module);
            }
            module.count++;
            if (entry.unread) {
                module.unread++;
            }
        }
        const items = [...modules.values()].sort((a, b) => a.label.localeCompare(b.label));
        return items.length ? [{ key: "modules", label: false, items }] : [];
    }

    /** Записи выбранной группы; порядок сервера -- позднее опубликованное сверху. */
    get activeEntries() {
        if (!this.state.activeKey) {
            return [];
        }
        return this.state.entries
            .filter((entry) => this._groupKey(entry) === this.state.activeKey)
            .map((entry) => {
                const doc = this.state.html[entryKey(entry)] || {};
                return {
                    ...entry,
                    key: entryKey(entry),
                    label: this.formatDayFull(entry.date),
                    // День записи нужен только ленте: в остальных режимах он
                    // уже вынесен в заголовок группы.
                    day: this.groupedByFeed ? this.formatDayFull(entry.date) : false,
                    // Время публикации -- в любом режиме: по нему записи и
                    // упорядочены, и днём записи оно не выводится.
                    stamp: this.formatStamp(entry),
                    // Заголовок записи идёт без даты: день и так рядом. Когда
                    // кроме даты в нём ничего не было, датовые режимы ставят
                    // название модуля, а режим модулей -- ничего: там оно уже
                    // стоит над всей группой.
                    heading: doc.heading || (this.groupedByModule ? false : entry.title),
                    html: doc.html,
                };
            });
    }

    get activeTitle() {
        if (!this.state.activeKey) {
            return "";
        }
        if (this.groupedByFeed) {
            return this.formatMonth(this.state.activeKey);
        }
        if (this.groupedByDate) {
            return this.formatDayFull(this.state.activeKey);
        }
        const entry = this.state.entries.find((item) => item.module === this.state.activeKey);
        return entry ? entry.title : this.state.activeKey;
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

    /**
     * Показать записи на выбранном языке. Индекс перезапрашивать незачем --
     * состав летописи от языка не зависит, -- а вот отрендеренный текст
     * приходится забыть и запросить заново.
     */
    async selectLanguage(code) {
        if (code === this.state.lang) {
            return;
        }
        this.state.lang = code;
        this.state.html = {};
        const key = this.state.activeKey;
        if (key) {
            await this.selectGroup(key);
        }
    }

    /** Подсказка к левой цифре строки: сколько записей группы не прочитано. */
    unreadTitle(item) {
        return sprintf(_t("%s unread"), item.unread);
    }

    /** Подсказка к правой цифре строки: сколько записей в группе всего. */
    countTitle(item) {
        return sprintf(_t("%s entries in total"), item.count);
    }

    get unreadCount() {
        return this.state.entries.filter((entry) => entry.unread).length;
    }

    async selectGroup(key) {
        // Подсветка прошлой группы снимается только сейчас: иначе жирный
        // шрифт и NEW пропадали бы прямо под курсором читателя.
        this._clearHighlight();
        // Записи прошлой группы уходят из DOM: наблюдатель пересоздастся на
        // новых элементах в onPatched. График при этом не перематываем: читатель
        // сам выбрал, какую часть архива держать перед глазами.
        this._stopObserver();
        this.state.activeKey = key;
        const wanted = this.state.entries.filter((entry) => this._groupKey(entry) === key);
        this._highlighted = wanted;
        // День и модуль показываются целиком, поэтому прочитаны целиком. Лента
        // месяца -- это десятки записей: их отмечает наблюдатель прокрутки.
        const markRead = !this.groupedByFeed;
        const missing = wanted.filter((entry) => !(entryKey(entry) in this.state.html));
        if (missing.length) {
            const data = await this.rpc("/odubook/change", {
                entries: missing.map((entry) => ({ module: entry.module, date: entry.date })),
                mark_read: markRead,
                lang: this.state.lang || undefined,
            });
            Object.assign(this.state.html, data.entries || {});
        }
        if (markRead) {
            for (const entry of wanted) {
                this._seen.add(entryKey(entry));
            }
        }
    }

    async setGroupBy(groupBy) {
        if (this.state.groupBy === groupBy) {
            return;
        }
        this.state.groupBy = groupBy;
        this.state.activeKey = null;
        // График рисуется заново -- он снова должен открыться на свежих месяцах.
        this._chartScrolled = false;
        const groups = this.archive;
        if (groups.length && groups[0].items.length) {
            await this.selectGroup(groups[0].items[0].key);
        }
    }

    /** Показать или убрать график месяцев; он снова откроется на свежем крае. */
    toggleChart() {
        this.state.showChart = !this.state.showChart;
        this._chartScrolled = false;
    }

    async markAllRead() {
        await this.rpc("/odubook/changes/read_all", {});
        this._highlighted = [];
        for (const entry of this.state.entries) {
            entry.unread = false;
            entry.is_new = false;
            this._seen.add(entryKey(entry));
        }
    }

    /**
     * Разобрать параметры ссылки на архив: режим, группа, запись и язык.
     * Значения приходят из адресной строки, поэтому проверяются здесь, а не
     * там, где применяются.
     */
    _linkParams() {
        const params = { ...router.current, ...this.props.action?.params };
        return {
            groupBy: GROUP_MODES.includes(params.group_by) ? params.group_by : null,
            group: params.group ? String(params.group) : null,
            entry: params.entry ? String(params.entry) : null,
            lang: params.book_lang ? String(params.book_lang) : undefined,
        };
    }

    /**
     * Группа, с которой открывается архив: названная в ссылке, содержащая
     * запись из ссылки или первая в списке.
     */
    _startGroupKey() {
        const groups = this.archive;
        const known = new Set();
        for (const group of groups) {
            for (const item of group.items) {
                known.add(item.key);
            }
        }
        if (this.link.group && known.has(this.link.group)) {
            return this.link.group;
        }
        if (this.link.entry) {
            const entry = this.state.entries.find(
                (item) => entryKey(item) === this.link.entry
            );
            if (entry) {
                return this._groupKey(entry);
            }
        }
        return groups.length && groups[0].items.length ? groups[0].items[0].key : null;
    }

    /** Ссылка на группу или запись архива: её читатель кладёт в буфер обмена. */
    _archiveUrl(params) {
        const hash = new URLSearchParams({
            action: "odubook.changes",
            group_by: this.state.groupBy,
            ...params,
        });
        if (this.state.lang) {
            hash.set("book_lang", this.state.lang);
        }
        return `${browser.location.origin}/odoo/action-${hash.get("action")}?${new URLSearchParams([...hash].filter(([key]) => key !== "action")).toString()}`;
    }

    /** Прочитать набор из хранилища браузера; битое значение -- пустой набор. */
    _restoreSelection() {
        let stored = null;
        try {
            stored = JSON.parse(browser.localStorage.getItem(SELECTION_KEY));
        } catch (error) {
            return [];
        }
        if (!Array.isArray(stored)) {
            return [];
        }
        return stored.filter((key) => typeof key === "string" && key.includes("|"));
    }

    /**
     * Запомнить набор. Хранилище бывает недоступно -- приватный режим,
     * переполнение, -- и это не повод ронять летопись: набор просто доживёт до
     * перезагрузки.
     */
    _saveSelection() {
        try {
            browser.localStorage.setItem(SELECTION_KEY, JSON.stringify(this.state.selection));
        } catch (error) {
            // Хранить негде: набор остаётся только в памяти вкладки.
        }
    }

    /** Запись отмечена галочкой: набор переживает смену группы, режима и языка. */
    isPicked(entry) {
        return this.state.selection.includes(entryKey(entry));
    }

    /** Добавить запись в набор или убрать её оттуда. */
    togglePick(entry) {
        const key = entryKey(entry);
        const index = this.state.selection.indexOf(key);
        if (index === -1) {
            this.state.selection.push(key);
        } else {
            this.state.selection.splice(index, 1);
        }
        this._saveSelection();
    }

    clearSelection() {
        this.state.selection = [];
        this._saveSelection();
    }

    /**
     * Отмеченные записи в порядке отметки. Ключ мог остаться от записи, которой
     * в летописи больше нет: такой ключ молча выпадает из набора.
     */
    get selectedEntries() {
        const known = new Map(this.state.entries.map((entry) => [entryKey(entry), entry]));
        return this.state.selection.map((key) => known.get(key)).filter(Boolean);
    }

    /** Скачать отмеченные записи одним PDF, в порядке отметки. */
    exportSelection() {
        const entries = this.selectedEntries;
        if (!entries.length) {
            return;
        }
        this.exportPdf(entries, _t("Selected changes"));
    }

    /** Адрес PDF: сервер собирает документ из перечисленных записей. */
    _pdfUrl(entries, title) {
        const query = new URLSearchParams({
            entries: entries.map((entry) => entryKey(entry)).join(","),
            title: title || "",
        });
        if (this.state.lang) {
            query.set("lang", this.state.lang);
        }
        return `/odubook/changes/pdf?${query.toString()}`;
    }

    /** Скачать статьи под заголовком одним PDF. */
    exportPdf(entries, title) {
        browser.open(this._pdfUrl(entries, title), "_blank");
    }

    /** Скачать все статьи открытой группы. */
    exportGroupPdf() {
        this.exportPdf(this.activeEntries, this.activeTitle);
    }

    /** Скачать одну запись. */
    exportEntryPdf(entry) {
        this.exportPdf([entry], entry.heading || this.activeTitle);
    }

    /** Положить в буфер обмена ссылку на открытую группу. */
    copyGroupLink() {
        this._copy(this._archiveUrl({ group: this.state.activeKey }));
    }

    /** Положить в буфер обмена ссылку на запись под этим заголовком. */
    copyEntryLink(entry) {
        this._copy(this._archiveUrl({ group: this.state.activeKey, entry: entry.key }));
    }

    /**
     * Скопировать ссылку и сказать об этом. Буфер обмена доступен не везде --
     * по HTTP его нет вовсе, -- поэтому при отказе показываем сам адрес: его
     * читатель скопирует руками.
     */
    async _copy(url) {
        try {
            await browser.navigator.clipboard.writeText(url);
        } catch (error) {
            this.notification.add(url, { title: _t("Copy this link"), sticky: true });
            return;
        }
        this.notification.add(_t("Link copied to the clipboard"), { type: "success" });
    }

    /**
     * Ссылка на запись ведёт к ней самой, а не к началу группы: после первой
     * отрисовки прокручиваем архив к этой записи, и только один раз.
     */
    _syncLinkScroll() {
        if (!this.link.entry || !this.root.el) {
            return;
        }
        const target = this.root.el.querySelector(
            `.o_odu_changes_entry[data-key="${CSS.escape(this.link.entry)}"]`
        );
        if (!target) {
            return;
        }
        this.link.entry = null;
        target.scrollIntoView({ block: "start" });
    }

    /** Снять «непрочитано»/NEW с записей, которые пользователь уже видел. */
    _clearHighlight() {
        for (const entry of this._highlighted || []) {
            // В ленте месяца непросмотренная запись остаётся непрочитанной.
            if (this._seen.has(entryKey(entry))) {
                entry.unread = false;
                entry.is_new = false;
            }
        }
        this._highlighted = [];
    }

    /**
     * Держать наблюдатель прокрутки в согласии с текущим режимом: в ленте
     * следим за записями, в остальных режимах он не нужен.
     */
    _syncObserver() {
        if (!this.groupedByFeed || typeof IntersectionObserver === "undefined") {
            this._stopObserver();
            return;
        }
        if (!this._observer) {
            this._observer = new IntersectionObserver(
                (records) => this._onEntriesVisible(records),
                { threshold: 0.15 }
            );
        }
        for (const el of this.root.el.querySelectorAll(".o_odu_changes_entry[data-key]")) {
            const key = el.dataset.key;
            if (this._observed.has(key) || this._seen.has(key)) {
                continue;
            }
            this._observed.add(key);
            this._observer.observe(el);
        }
    }

    /**
     * Длинный архив не влезает в ширину графика, поэтому при первом показе он
     * открывается на свежих месяцах -- на правом краю.
     */
    _syncChartScroll() {
        const box = this.root.el && this.root.el.querySelector(".o_odu_chart_scroll");
        if (!box) {
            this._chartScrolled = false;
            return;
        }
        if (this._chartScrolled) {
            return;
        }
        box.scrollLeft = box.scrollWidth;
        this._chartScrolled = true;
    }

    _stopObserver() {
        if (this._observer) {
            this._observer.disconnect();
            this._observer = null;
        }
        this._observed.clear();
    }

    /** Записи, доскроллленные читателем, отмечаются прочитанными на сервере. */
    _onEntriesVisible(records) {
        const fresh = [];
        for (const record of records) {
            if (!record.isIntersecting) {
                continue;
            }
            const key = record.target.dataset.key;
            this._observer.unobserve(record.target);
            this._observed.delete(key);
            if (this._seen.has(key)) {
                continue;
            }
            this._seen.add(key);
            const [module, date] = key.split("|");
            fresh.push({ module, date });
        }
        if (fresh.length) {
            this.rpc("/odubook/changes/read", { entries: fresh });
        }
    }

    formatMonth(key) {
        return DateTime.fromFormat(key, "yyyy-MM").toFormat("LLLL yyyy");
    }

    formatMonthShort(key) {
        return DateTime.fromFormat(key, "yyyy-MM").toFormat("LLL");
    }

    formatDayShort(date) {
        return DateTime.fromISO(date).toFormat("ccc, d");
    }

    formatDayFull(date) {
        return DateTime.fromISO(date).toFormat("d LLLL yyyy");
    }

    /**
     * Когда запись влилась в prod, в часовом поясе читателя. Записи ветки,
     * которую ещё не влили, честно говорят об этом: время публикации у них
     * не наступило.
     */
    formatStamp(entry) {
        if (!entry.published) {
            return _t("Not published yet");
        }
        // Сервер отдаёт UTC в формате Odoo: "YYYY-MM-DD HH:MM:SS".
        const published = DateTime.fromISO(entry.published.replace(" ", "T"), { zone: "utc" });
        if (!published.isValid) {
            return _t("Not published yet");
        }
        return sprintf(
            _t("Published %s"),
            published.toLocal().toFormat("d LLLL yyyy, HH:mm")
        );
    }
}

ChangesApp.props = { ...standardActionServiceProps };
ChangesApp.template = "odubook.ChangesApp";

registry.category("actions").add("odubook.changes", ChangesApp);
