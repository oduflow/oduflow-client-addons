/** @odoo-module **/
import { Component, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { _t } from "@web/core/l10n/translation";
import { VoiceRecorder, isVoiceRecordingSupported } from "@odupilot/js/voice_recorder";

function blobBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(reader.error);
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
        reader.readAsDataURL(blob);
    });
}
export class VoiceTextField extends Component {
    static template = "odupilot.VoiceTextField";
    static props = { ...standardFieldProps, placeholder: { type: String, optional: true } };
    setup() {
        this.orm = useService("orm");
        this.state = useState({ recording: false, transcribing: false, duration: 0, error: "" });
        this.canRecord = isVoiceRecordingSupported();
        this.disposed = false;
        onWillUnmount(() => {
            this.disposed = true;
            if (this.recorder) { this.recorder.handlers = {}; this.recorder.stop(); this.recorder.release(); }
        });
    }
    get value() { return this.props.record.data[this.props.name] || ""; }
    get duration() {
        return String(Math.floor(this.state.duration / 60)).padStart(2, "0") + ":" + String(this.state.duration % 60).padStart(2, "0");
    }
    onInput(event) { return this.props.record.update({ [this.props.name]: event.target.value }); }
    async onRecord() {
        this.state.error = ""; this.state.duration = 0;
        this.recorder = new VoiceRecorder({
            onTick: seconds => { this.state.duration = seconds; },
            onStop: (blob, seconds, mimeType) => this.transcribe(blob, seconds, mimeType),
        });
        try {
            await this.recorder.start();
            if (this.disposed) { this.recorder.handlers = {}; this.recorder.stop(); this.recorder.release(); return; }
            this.state.recording = true;
        } catch {
            this.recorder?.release();
            this.state.error = _t("Microphone access was denied. Allow it in the browser to dictate a developer request.");
        }
    }
    onStop() { this.recorder?.stop(); this.state.recording = false; }
    async transcribe(blob, seconds, mimeType) {
        if (this.disposed) { return; }
        this.state.recording = false;
        if (!blob?.size) { this.state.error = _t("The voice recording is empty."); return; }
        this.state.transcribing = true;
        try {
            const audio = await blobBase64(blob);
            const transcript = await this.orm.call("odupilot.developer.wizard", "transcribe_voice", [audio, VoiceRecorder.buildFileName(mimeType), mimeType, seconds]);
            if (!this.disposed) {
                const current = this.value.trim();
                await this.props.record.update({ [this.props.name]: current ? current + "\n\n" + transcript : transcript });
            }
        } catch (error) {
            this.state.error = error.data?.message || _t("Voice transcription failed. Try again or type the request.");
        } finally { this.state.transcribing = false; this.recorder = undefined; }
    }
}
registry.category("fields").add("ai_voice_text", { component: VoiceTextField, supportedTypes: ["text"], extractProps: ({ attrs }) => ({ placeholder: attrs.placeholder }) });
