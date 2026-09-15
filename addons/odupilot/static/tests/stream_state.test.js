import { describe, expect, test } from "@odoo/hoot";
/** @odoo-module **/

import {
    applyStreamUpdate,
    streamStateFromSnapshot,
    STREAM_PART_LIMIT,
} from '@odupilot/js/stream_state';

const snapshot = (parts, seq = 1) => streamStateFromSnapshot({
    parts,
    seq,
    text: parts.filter(part => part.type === 'text')
        .map(part => part.text || '').join('\n\n'),
});

describe("OduPilot live answer state", () => {

    test('appends a text delta to the part it belongs to', () => {
        const state = snapshot([{id: 'p1', type: 'text', text: 'Hello'}]);

        const applied = applyStreamUpdate(state, {
            seq: 2, parts_delta: [{id: 'p1', append: ' world'}],
        });

        expect(applied).toBe(true);
        expect(state.parts[0].text).toBe('Hello world');
        expect(state.text).toBe('Hello world');
    });

    test('adds a new part and replaces a known one', () => {
        const state = snapshot([{id: 'p1', type: 'tool', tool: 'read', status: 'running'}]);

        applyStreamUpdate(state, {
            seq: 2, parts_delta: [{id: 'p2', type: 'text', text: 'Answer'}],
        });
        applyStreamUpdate(state, {
            seq: 3,
            parts_delta: [{id: 'p1', type: 'tool', tool: 'read', status: 'completed'}],
        });

        expect(state.parts.length).toBe(2);
        expect(state.parts[0].status).toBe('completed');
        expect(state.parts[1].text).toBe('Answer');
    });

    test('reports a gap instead of guessing', () => {
        const state = snapshot([{id: 'p1', type: 'text', text: 'Hello'}]);

        expect(applyStreamUpdate(state, {
            seq: 4, parts_delta: [{id: 'p1', append: '!'}],
        })).toBe(false);
        expect(applyStreamUpdate(state, {
            seq: 2, parts_delta: [{id: 'unknown', append: '!'}],
        })).toBe(false);
    });

    test('keeps only the last parts, like the server', () => {
        const parts = [];
        for (let index = 0; index < STREAM_PART_LIMIT; index++) {
            parts.push({id: `p${index}`, type: 'text', text: `step ${index}`});
        }
        const state = snapshot(parts);

        applyStreamUpdate(state, {
            seq: 2, parts_delta: [{id: 'tail', type: 'text', text: 'last'}],
        });

        expect(state.parts.length).toBe(STREAM_PART_LIMIT);
        expect(state.parts[STREAM_PART_LIMIT - 1].id).toBe('tail');
    });
});
