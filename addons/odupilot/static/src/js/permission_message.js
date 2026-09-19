/** @odoo-module **/
import { markup, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { Message } from "@mail/components/message/message";
import { ThreadView as Thread } from "@mail/components/thread_view/thread_view";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { applyStreamUpdate, streamStateFromSnapshot } from "@odupilot/js/stream_state";
const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
function renderStreamText(text) {
    return escape(text).replace(/\n/g, '<br>');
}

function renderStreamTrace(kind, icon, summary, body) {
    // Служебный блок свёрнут и в живом следе: раскрытая цепочка рассуждений и
    // вызовов инструментов прокручивает разговор сама по себе, а прогресс
    // виден по заголовку группы и строке состояния сессии.
    return `<details class="o_AiChatTrace o_AiChatTrace_${kind}">` +
        `<summary class="o_AiChatTrace_summary">` +
        `<i class="fa ${icon}" aria-hidden="true"></i> ${escape(summary)}` +
        `</summary>` +
        `<div class="o_AiChatTrace_body">${body}</div></details>`;
}

/**
 * Заголовок группы служебных шагов: сколько их и какими инструментами.
 *
 * @param {Object[]} parts
 * @returns {string}
 */
function streamGroupSummary(parts) {
    const tools = [];
    for (const part of parts) {
        if (part.type === 'tool' && part.tool && !tools.includes(part.tool)) {
            tools.push(part.tool);
        }
    }
    const summary = parts.length === 1
        ? _t('AI work: 1 step')
        : _t('AI work: %s steps', parts.length);
    if (!tools.length) {
        return summary;
    }
    const shown = tools.slice(0, 3).join(', ') + (tools.length > 3 ? ', …' : '');
    return `${summary} (${shown})`;
}

function renderStreamGroup(parts) {
    if (!parts.length) {
        return '';
    }
    const rendered = parts.map(part => part.type === 'tool'
        ? renderStreamTool(part)
        : renderStreamTrace(
            'reasoning',
            'fa-lightbulb-o',
            _t('AI reasoning'),
            `<div>${renderStreamText(part.text)}</div>`,
        )).join('');
    if (parts.length === 1) {
        return rendered;
    }
    return renderStreamTrace(
        'group', 'fa-tasks', streamGroupSummary(parts), rendered);
}

function renderStreamToolValue(label, value) {
    if (!value) {
        return '';
    }
    return `<p class="o_AiChatTrace_label">${escape(label)}</p>` +
        `<pre class="o_AiChatTrace_code">${escape(value)}</pre>`;
}

function renderStreamTool(part) {
    const statuses = {
        error: _t('Tool call failed'),
        pending: _t('Tool call requested'),
        running: _t('Tool call in progress'),
    };
    const status = statuses[part.status] || _t('Tool call finished');
    const summary = part.tool ? `${status}: ${part.tool}` : status;
    const body = (part.title ? `<p class="o_AiChatTrace_title">${escape(part.title)}</p>` : '') +
        renderStreamToolValue(_t('Tool input'), part.input) +
        renderStreamToolValue(_t('Tool output'), part.output);
    return renderStreamTrace('tool', 'fa-wrench', summary, body);
}

function renderStreamBody(stream) {
    const chunks = [];
    let group = [];
    const flushGroup = () => {
        const rendered = renderStreamGroup(group);
        group = [];
        if (rendered) {
            chunks.push(rendered);
        }
    };
    for (const part of stream.parts || []) {
        if ((part.type === 'reasoning' && part.text) || part.type === 'tool') {
            // Идущие подряд служебные шаги — одной свёрнутой группой, как и в
            // сохранённых сообщениях разговора.
            group.push(part);
            continue;
        }
        if (part.type === 'text' && part.text) {
            flushGroup();
            chunks.push(`<span class="o_AiChatStream_text">${renderStreamText(part.text)}</span>`);
        }
    }
    flushGroup();
    if (!chunks.length && stream.text) {
        chunks.push(`<span class="o_AiChatStream_text">${renderStreamText(stream.text)}</span>`);
    }
    if (!chunks.length) {
        return `<span class="o_AiChatStream_waiting">${escape(_t('AI is responding…'))}</span>`;
    }
    chunks.push('<span class="o_AiChatStream_cursor" aria-hidden="true"></span>');
    return chunks.join('');
}


patch(Message.prototype, "odupilot.message", {
    setup() { this._super(...arguments); this.odupilotState = useState({ submitting: false }); },
    async replyOduPilot(event) {
        const kind = event.currentTarget.dataset.kind;
        const data = this.props.record.message[`odupilot_${kind}`];
        if (this.odupilotState.submitting || data?.status !== "pending") { return; }
        const response = event.currentTarget.dataset.response;
        this.odupilotState.submitting = true;
        try {
            this.props.record.message.update({ [`odupilot_${kind}`]: await this.env.services.orm.call(
                `odupilot.${kind}`, "action_reply", [[data.id], response]) });
        } finally { this.odupilotState.submitting = false; }
    },
});
const streamVersions = new WeakMap();
async function refreshStream(orm, thread) {
    const version = streamVersions.get(thread) || 0;
    const snapshot = await orm.call("odupilot.session", "stream_snapshot", [thread.id]);
    // A newer event (especially done/error) wins over an in-flight snapshot.
    if ((streamVersions.get(thread) || 0) === version) {
        thread.update({ odupilot_stream: snapshot ? streamStateFromSnapshot(snapshot) : null });
    }
}
patch(Thread.prototype, "odupilot.thread", {
    setup() {
        this._super(...arguments);
        const load = (thread) => thread.is_odupilot ? refreshStream(this.env.services.orm, thread) : undefined;
        onWillStart(() => load(this.props.record.thread));
        onWillUpdateProps((next) => {
            if (next.record.thread.id !== this.props.record.thread.id) { return load(next.record.thread); }
        });
    },
    get odupilotStatus() {
        const status = this.props.record.thread.odupilot_session;
        if (!status) { return null; }
        const labels = { init: _t("Initializing AI session…"), ready: _t("AI session is ready"), busy: _t("AI is working…"), waiting_approval: _t("Waiting for approval"), error: _t("AI session failed"), closed: _t("AI session is closed") };
        return { ...status, label: labels[status.state] || status.state };
    },
    get odupilotLiveBody() {
        return this.props.record.thread.odupilot_stream ? markup(renderStreamBody(this.props.record.thread.odupilot_stream)) : "";
    },
});
registry.category("services").add("odupilot.live", {
    dependencies: ["bus_service", "messaging", "orm", "notification", "action"],
    async start(env, { bus_service, messaging, orm, notification, action }) {
        const store = await messaging.get();
        const bus = { subscribe(type, callback) {
            bus_service.addEventListener("notification", ({ detail }) => {
                for (const event of detail) { if (event.type === type) { callback(event.payload); } }
            });
        } };
        bus.subscribe("odupilot/chatter", (data) => env.bus.trigger("odupilot/chatter", data));
        const getThread = (id) => store.models.Thread.findFromIdentifyingData({ model: "mail.channel", id });
        for (const kind of ["permission", "recovery"]) {
            bus.subscribe(`odupilot.${kind}/updated`, (data) => {
                const message = store.models.Message.findFromIdentifyingData({ id: data.message_id });
                if (message) { message.update({ [`odupilot_${kind}`]: data }); }
            });
        }
        bus.subscribe("odupilot.session/status", (status) => {
            const thread = getThread(status.channel_id);
            if (thread) { thread.update({ odupilot_session: status }); }
        });
        bus.subscribe("odupilot_stream/update", async (stream) => {
            const thread = getThread(stream.channel_id);
            if (!thread) { return; }
            streamVersions.set(thread, (streamVersions.get(thread) || 0) + 1);
            if (["done", "error"].includes(stream.state)) {
                thread.update({ odupilot_stream: null });
                return;
            }
            if (stream.state === "start") { thread.update({ odupilot_stream: streamStateFromSnapshot(stream) }); }
            else if (!applyStreamUpdate(thread.odupilot_stream, stream)) {
                await refreshStream(orm, thread);
            }
        });
        bus.subscribe("odupilot/assigned", (data) => notification.add(data.body, {
            title: _t("AI Developer"), sticky: true,
            buttons: [{ name: _t("Open conversation"), onClick: async () => action.doAction(await orm.call("odupilot.session", "action_open_channel", [[data.res_id]])) }],
        }));
    },
});
