/** @odoo-module **/

// Зеркала серверных ограничений из odupilot_session.py: сервер режет свою
// копию так же, поэтому одинаковые пределы держат обе стороны в согласии.
export const STREAM_TEXT_LIMIT = 200000;
export const STREAM_PART_LIMIT = 60;

/**
 * Состояние живого следа из полного снимка ('start' или ответ RPC).
 *
 * @param {Object} payload
 * @returns {Object}
 */
export function streamStateFromSnapshot(payload) {
    return {
        parts: (payload.parts || []).map(part => Object.assign({}, part)),
        seq: payload.seq || 0,
        text: payload.text || '',
    };
}

/**
 * Наложить приращение на известное состояние.
 *
 * Возвращает false, когда приращение положить не на что: пропущено
 * уведомление или дописать просят часть, которой у клиента нет. В этом случае
 * состояние надо перезапросить снимком, а не догадываться.
 *
 * @param {Object} state
 * @param {Object} payload
 * @returns {boolean}
 */
export function applyStreamUpdate(state, payload) {
    if (!state) {
        return false;
    }
    const seq = payload.seq || 0;
    if (seq !== state.seq + 1) {
        return false;
    }
    for (const delta of payload.parts_delta || []) {
        const existing = state.parts.find(part => part.id === delta.id);
        if (delta.append !== undefined) {
            if (!existing) {
                return false;
            }
            existing.text = ((existing.text || '') + delta.append)
                .slice(-STREAM_TEXT_LIMIT);
        } else if (existing) {
            Object.assign(existing, delta);
        } else {
            state.parts.push(Object.assign({}, delta));
        }
    }
    if (state.parts.length > STREAM_PART_LIMIT) {
        state.parts = state.parts.slice(-STREAM_PART_LIMIT);
    }
    state.text = state.parts
        .filter(part => part.type === 'text')
        .map(part => part.text || '')
        .join('\n\n')
        .slice(-STREAM_TEXT_LIMIT);
    state.seq = seq;
    return true;
}
