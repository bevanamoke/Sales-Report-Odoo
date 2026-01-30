/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillUpdateProps } from "@odoo/owl"; 

export class ProductCategoryReportWidget extends Component {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        
        // Initialize report data
        this.reportData = this._parseReportData(this.props.record.data.report_data_json);
        
        // Update when props change
        onWillUpdateProps((nextProps) => {
            this.reportData = this._parseReportData(nextProps.record.data.report_data_json);
        });
    }

    /**
     * Parses the JSON string from the report_data_json field
     */
    _parseReportData(jsonValue) {
        const defaultData = {
            rows: [
                { id: 1, name: "All" },
                { id: 2, name: "Total" }
            ],
            columns: [
                { id: 1, name: "SAL CAPITEM CLAVIN" },
                { id: 2, name: "SAL Kitchen" }
            ],
            values: {
                "1_1": 0.00,
                "1_2": 0.00,
                "2_1": 0.00,
                "2_2": 0.00
            },
            row_totals: {
                1: 0.00,
                2: 0.00
            },
            column_totals: {
                1: 0.00,
                2: 0.00
            },
            grand_total: 0.00,
            has_data: false
        };

        if (!jsonValue) {
            return defaultData;
        }
        try {
            const parsedData = JSON.parse(jsonValue);
            // Always show the table structure, even with no real data
            if (!parsedData.rows || parsedData.rows.length === 0) {
                parsedData.rows = defaultData.rows;
            }
            if (!parsedData.columns || parsedData.columns.length === 0) {
                parsedData.columns = defaultData.columns;
            }
            if (!parsedData.values) {
                parsedData.values = defaultData.values;
            }
            parsedData.has_data = true; // Always show table
            return parsedData;
        } catch (e) {
            console.error("Failed to parse report_data_json:", e);
            return defaultData;
        }
    }

    /**
     * Format amount for display
     */
    formatAmount(amount) {
        if (amount === undefined || amount === null) {
            return '0.00';
        }
        
        const number = parseFloat(amount);
        if (isNaN(number)) {
            return '0.00';
        }
        
        // Format exactly as shown: 2 decimal places, no thousands separators
        return number.toFixed(2);
    }

    /**
     * Get the amount for a specific category and customer
     */
    getAmount(categoryId, customerId) {
        const key = `${categoryId}_${customerId}`;
        return this.reportData.values[key] || 0;
    }

    /**
     * Get row total for a category
     */
    getRowTotal(categoryId) {
        return this.reportData.row_totals[categoryId] || 0;
    }

    /**
     * Get column total for a customer
     */
    getColumnTotal(customerId) {
        return this.reportData.column_totals[customerId] || 0;
    }

    /**
     * Print actions
     */
    async onPrintReport(reportType) {
        const record = this.props.record;
        await record.model.root.save();
        
        if (reportType === 'xls') {
            await record.model.root.executeAction('print_xls_report', {});
        } else if (reportType === 'pdf') {
            await record.model.root.executeAction('print_pdf_report', {});
        }
    }

    /**
     * Cancel action
     */
    async onCancel() {
        // Close the dialog or go back
        this.env.services.action.doAction({ type: 'ir.actions.act_window_close' });
    }

    /**
     * Always show table (modified to always return true)
     */
    get hasData() {
        return true; // Always show the table structure
    }
}

// --------------------------------------------------------------------------------
// TEMPLATE
// --------------------------------------------------------------------------------

ProductCategoryReportWidget.template = "sales_store_expense_report.ProductCategoryReportWidget";

// Register the widget
registry.category("fields").add("product_category_report_widget", {
    component: ProductCategoryReportWidget,
});