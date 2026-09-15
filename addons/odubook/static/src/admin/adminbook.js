/** @odoo-module **/

import { registry } from "@web/core/registry";
import { BookApp } from "@odubook/book/book";

/**
 * Книга администратора использует общий UI и защищённый endpoint.
 */
export class AdminBookApp extends BookApp {
}

AdminBookApp.endpoint = "/odubook/admin";
AdminBookApp.action = "odubook.admin";
AdminBookApp.book = "admin";

registry.category("actions").add("odubook.admin", AdminBookApp);
