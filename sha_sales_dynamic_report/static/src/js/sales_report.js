/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUnmount, useExternalListener } from "@odoo/owl";

class SalespersonReport extends Component {
    static template = "salesperson_report.SalespersonReportTemplate";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            reportType: "detail",
            summaryGroupBy: "salesperson",
            trendPeriod: "month",
            agingBucket: "delivery",
            darkMode: this.getPreferredDarkMode(),
            dateFrom: this.defaultDateFrom(),
            dateTo: this.today(),
            salespersonIds: [],
            productIds: [],
            categoryIds: [],
            customerIds: [],
            saleOrderStatuses: [],
            search: "",
            groups: [],
            salespersons: [],
            products: [],
            categories: [],
            customers: [],
            statuses: [],
            salespersonDropdown: false,
            productDropdown: false,
            categoryIdsDropdown: false,
            customerIdsDropdown: false,
            saleOrderStatusesDropdown: false,
            salespersonSearch: "",
            productSearch: "",
            categorySearch: "",
            customerSearch: "",
            minDiscount: "",
            maxDiscount: "",
            minMargin: "",
            maxMargin: "",
            includeZeroMargin: false,
            includeNegativeMargin: true,
            deliveryStatuses: [],
            invoiceStatuses: [],
            collapsed: {},
            loading: true,
            offset: 0,
            totalCount: 0,
            hasMore: false,
        });
        this._searchTimer = null;
        this._darkModeManual = false;
        this._darkModeMedia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
        if (this._darkModeMedia) {
            this._darkModeMediaListener = (event) => {
                if (!this._darkModeManual) this.state.darkMode = event.matches;
            };
            this._darkModeMedia.addEventListener('change', this._darkModeMediaListener);
        }
        this._darkModeObserver = new MutationObserver(() => {
            if (!this._darkModeManual) this.state.darkMode = this.getPreferredDarkMode();
        });
        this._darkModeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
        if (document.body) this._darkModeObserver.observe(document.body, { attributes: true, attributeFilter: ['class', 'data-theme'] });
        onWillUnmount(() => {
            this._darkModeObserver.disconnect();
            if (this._darkModeMedia) this._darkModeMedia.removeEventListener('change', this._darkModeMediaListener);
        });

        useExternalListener(document, "click", (ev) => {
            if (this.state.salespersonDropdown && !ev.target.closest(".o_sha_multi")) {
                this.state.salespersonDropdown = false;
            }
            if (this.state.productDropdown && !ev.target.closest(".o_sha_multi")) {
                this.state.productDropdown = false;
            }
            if (this.state.categoryIdsDropdown && !ev.target.closest(".o_sha_multi")) {
                this.state.categoryIdsDropdown = false;
            }
            if (this.state.customerIdsDropdown && !ev.target.closest(".o_sha_multi")) {
                this.state.customerIdsDropdown = false;
            }
            if (this.state.saleOrderStatusesDropdown && !ev.target.closest(".o_sha_multi")) {
                this.state.saleOrderStatusesDropdown = false;
            }
        });

        onWillStart(async () => {
            const options = await this.orm.call("salesperson.report", "get_filter_options", []);
            this.state.salespersons = options.salespersons || [];
            this.state.products = options.products || [];
            this.state.categories = options.categories || [];
            this.state.customers = options.customers || [];
            this.state.statuses = options.sale_order_statuses || [];
            await this.fetchData();
        });
    }

    today() {
        const now = new Date();
        const pad = (value) => String(value).padStart(2, "0");
        return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    }

    getPreferredDarkMode() {
        const roots = [document.documentElement, document.body];
        const nativeDark = roots.some((node) => node && (node.classList.contains('o_dark') || node.classList.contains('o_dark_mode') || node.dataset.theme === 'dark'));
        return nativeDark || !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    }

    defaultDateFrom() {
        const d = new Date();
        d.setMonth(d.getMonth() - 1);
        const pad = (value) => String(value).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    async fetchData() {
        this.state.loading = true;
        const data = await this.orm.call("salesperson.report", "get_report_data", [], {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            salesperson_ids: this.state.salespersonIds,
            product_ids: this.state.productIds,
            category_ids: this.state.categoryIds,
            customer_ids: this.state.customerIds,
            min_discount: this.state.minDiscount || false,
            max_discount: this.state.maxDiscount || false,
            min_margin: this.state.minMargin || false,
            max_margin: this.state.maxMargin || false,
            include_zero_margin: this.state.includeZeroMargin,
            include_negative_margin: this.state.includeNegativeMargin,
            delivery_statuses: this.state.deliveryStatuses.join(","),
            invoice_statuses: this.state.invoiceStatuses.join(","),
            sale_order_statuses: this.state.saleOrderStatuses,
            search: this.state.search,
            report_type: this.state.reportType,
            summary_group_by: this.state.summaryGroupBy,
            trend_period: this.state.trendPeriod,
            aging_bucket: this.state.agingBucket,
            offset: this.state.offset,
            limit: 200,
        });
        this.state.groups = data.groups || [];
        this.state.totalCount = data.total_count || 0;
        this.state.hasMore = !!data.has_more;
        this.state.loading = false;
    }

    onFilterChange(field, ev) {
        this.state[field] = ev.target.value;
        if (field === "reportType" || field === "summaryGroupBy" || field === "trendPeriod" || field === "agingBucket") this.state.offset = 0;
        this.fetchData();
    }

    toggleDropdown(field) {
        this.state.salespersonDropdown = field === "salespersonIds" ? !this.state.salespersonDropdown : false;
        this.state.productDropdown = field === "productIds" ? !this.state.productDropdown : false;
        this.state.categoryIdsDropdown = field === "categoryIds" ? !this.state.categoryIdsDropdown : false;
        this.state.customerIdsDropdown = field === "customerIds" ? !this.state.customerIdsDropdown : false;
        this.state.saleOrderStatusesDropdown = field === "saleOrderStatuses" ? !this.state.saleOrderStatusesDropdown : false;
    }

    onMultiSearchInput(field, ev) {
        this.state[field] = ev.target.value;
    }

    get filteredSalespersons() {
        const term = (this.state.salespersonSearch || "").trim().toLowerCase();
        const selected = this.state.salespersons.filter((item) => this.state.salespersonIds.includes(item.id));
        const matched = !term
            ? this.state.salespersons
            : this.state.salespersons.filter((item) => item.name.toLowerCase().includes(term));
        return [...new Map([...selected, ...matched].map((item) => [item.id, item])).values()];
    }

    get filteredProducts() {
        const term = (this.state.productSearch || "").trim().toLowerCase();
        const selected = this.state.products.filter((item) => this.state.productIds.includes(item.id));
        const matched = !term
            ? this.state.products
            : this.state.products.filter((item) => item.display_name.toLowerCase().includes(term));
        return [...new Map([...selected, ...matched].map((item) => [item.id, item])).values()];
    }

    get filteredCategories() {
        const term = (this.state.categorySearch || "").trim().toLowerCase();
        const selected = this.state.categories.filter((item) => this.state.categoryIds.includes(item.id));
        const matched = !term ? this.state.categories : this.state.categories.filter((item) => (item.display_name || "").toLowerCase().includes(term));
        return [...new Map([...selected, ...matched].map((item) => [item.id, item])).values()];
    }

    get filteredCustomers() {
        const term = (this.state.customerSearch || "").trim().toLowerCase();
        const selected = (this.state.customers || []).filter((item) => this.state.customerIds.includes(item.id));
        const matched = !term ? (this.state.customers || []) : (this.state.customers || []).filter((item) => (item.display_name || "").toLowerCase().includes(term));
        return [...new Map([...selected, ...matched].map((item) => [item.id, item])).values()];
    }

    toggleMulti(field, id) {
        const current = this.state[field];
        const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
        this.state[field] = next;
        this.state.offset = 0;
        this.fetchData();
    }

    clearMulti(field) {
        if (this.state[field].length) {
            this.state[field] = [];
            this.fetchData();
        }
    }

    clearMultiSearch(field) {
        if (this.state[field]) {
            this.state[field] = "";
        }
    }

    get groupByLabel() {
        return {
            salesperson: "Salesperson",
            customer: "Customer",
            product: "Product",
            category: "Product Category",
        }[this.state.summaryGroupBy] || "Salesperson";
    }

    get reportTitle() {
        const titles = {
            detail: "Sales Order Details",
            summary: "Sales Summary",
            discount_margin: "Discount and Margin",
            delivery_invoice: "Delivery and Invoicing Status",
            day_wise: "Sales Day Wise Report",
            trend: "Revenue, Qty and Margin Trend",
            aging: "Aging Report",
        };
        const base = titles[this.state.reportType] || "Sales Report";
        return (this.state.reportType === "detail" || this.state.reportType === "summary")
            ? `${base} by ${this.groupByLabel}`
            : base;
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.fetchData(), 250);
    }

    clearAll() {
        this.state.dateFrom = "";
        this.state.dateTo = "";
        this.state.salespersonIds = [];
        this.state.productIds = [];
            this.state.offset = 0;
        this.state.salespersonSearch = "";
        this.state.productSearch = "";
        this.state.categorySearch = "";
        this.state.customerSearch = "";
        this.state.categoryIds = [];
        this.state.customerIds = [];
        this.state.saleOrderStatuses = [];
        this.state.trendPeriod = "month";
        this.state.agingBucket = "delivery";
        this.state.offset = 0;
        this.state.search = "";
        this.fetchData();
    }

    toggleGroup(key) {
        this.state.collapsed[key] = !this.state.collapsed[key];
    }

    toggleGroupIfDetail(key) {
        if (this.state.reportType === "detail") this.toggleGroup(key);
    }

    toggleDarkMode() {
        this._darkModeManual = true;
        this.state.darkMode = !this.state.darkMode;
    }

    get activeFilters() {
        const list = [];
        if (this.state.dateFrom) list.push({ key: "dateFrom", label: "From: " + this.state.dateFrom });
        if (this.state.dateTo) list.push({ key: "dateTo", label: "To: " + this.state.dateTo });
        if (this.state.salespersonIds.length) {
            list.push({ key: "salespersonIds", label: "Salespersons (" + this.state.salespersonIds.length + ")" });
        }
        if (this.state.productIds.length) {
            list.push({ key: "productIds", label: "Products (" + this.state.productIds.length + ")" });
        }
        if (this.state.saleOrderStatuses.length) list.push({ key: "saleOrderStatuses", label: "Statuses (" + this.state.saleOrderStatuses.length + ")" });
        if (this.state.categoryIds.length) list.push({ key: "categoryIds", label: "Categories (" + this.state.categoryIds.length + ")" });
        if (this.state.customerIds.length) list.push({ key: "customerIds", label: "Customers (" + this.state.customerIds.length + ")" });
        if (this.state.search) list.push({ key: "search", label: '"' + this.state.search + '"' });
        return list;
    }

    removeFilter(key) {
        if (key === "salespersonIds") {
            this.state.salespersonIds = [];
            this.state.salespersonSearch = "";
        } else if (key === "productIds") {
            this.state.productIds = [];
            this.state.productSearch = "";
        } else if (key === "saleOrderStatus") {
            this.state.saleOrderStatuses = [];
        } else if (key === "categoryIds") {
            this.state.categoryIds = [];
            this.state.categorySearch = "";
        } else if (key === "customerIds") {
            this.state.customerIds = [];
            this.state.customerSearch = "";
        } else if (key === "saleOrderStatuses") {
            this.state.saleOrderStatuses = [];
        } else {
            this.state[key] = "";
        }
        this.fetchData();
    }

    exportParams() {
        return new URLSearchParams({
            date_from: this.state.dateFrom || "",
            date_to: this.state.dateTo || "",
            salesperson_ids: this.state.salespersonIds.join(","),
            product_ids: this.state.productIds.join(","),
            category_ids: this.state.categoryIds.join(","),
            customer_ids: this.state.customerIds.join(","),
            min_discount: this.state.minDiscount || "",
            max_discount: this.state.maxDiscount || "",
            min_margin: this.state.minMargin || "",
            max_margin: this.state.maxMargin || "",
            include_zero_margin: this.state.includeZeroMargin,
            include_negative_margin: this.state.includeNegativeMargin,
            sale_order_statuses: this.state.saleOrderStatuses.join(","),
            report_type: this.state.reportType,
            summary_group_by: this.state.summaryGroupBy,
            trend_period: this.state.trendPeriod,
            aging_bucket: this.state.agingBucket,
            search: this.state.search,
        }).toString();
    }

    exportExcel() {
        window.location = "/sha_sales_dynamic_report/export_xlsx?" + this.exportParams();
    }

    exportPdf() {
        window.location = "/sha_sales_dynamic_report/export_pdf?" + this.exportParams();
    }

    fmtMoney(v, symbol = "", position = "before") {
        const amount = (v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return position === "after" ? amount + symbol : symbol + amount;
    }

    fmtNumber(v, digits = 2) {
        return (Number(v || 0)).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
    }

    nextPage() { if (this.state.hasMore) { this.state.offset += 200; this.fetchData(); } }
    previousPage() { if (this.state.offset) { this.state.offset = Math.max(0, this.state.offset - 200); this.fetchData(); } }
}

registry.category("actions").add("sha_salesperson_report_action", SalespersonReport);

export default SalespersonReport;
