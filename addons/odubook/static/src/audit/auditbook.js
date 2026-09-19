/** @odoo-module **/

import { registry } from "@web/core/registry";
import { BookApp } from "@odubook/book/book";

export class AuditBookApp extends BookApp {}

AuditBookApp.endpoint = "/odubook/audit";
AuditBookApp.action = "odubook.audit";
AuditBookApp.book = "audit";

registry.category("actions").add("odubook.audit", AuditBookApp);
