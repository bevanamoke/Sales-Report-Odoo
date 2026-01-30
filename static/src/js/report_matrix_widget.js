/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl"; 

export class ReportMatrixWidget extends Component {
    setup() {
        super.setup();
        this.orm = useService("orm");
        
        // Initialize report data
        this.reportData = this._parseReportData(this.props.record.data.report_data_json);
    }

    willUpdateProps(nextProps) {
        this.reportData = this._parseReportData(nextProps.record.data.report_data_json);
    }

    /**
     * Parses the JSON string from the report_data_json field
     */
    _parseReportData(jsonValue) {
        const defaultData = {
            grouped_data: {},
            columns: [],
            date_from: false,
            date_to: false,
            model_context: 'default',
            has_data: false,
            report_type: 'detailed_lines'
        };

        if (!jsonValue) {
            return defaultData;
        }
        try {
            return JSON.parse(jsonValue);
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
        
        // Format with thousands separators and 2 decimal places
        return number.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    /**
     * Format quantity with unit of measurement
     */
    formatQuantity(quantity, uom) {
        if (quantity === undefined || quantity === null) {
            return '0';
        }
        return `${quantity} ${uom || ''}`.trim();
    }

    /**
     * Get location groups for display with unique keys
     */
    get locationGroups() {
        const groups = Object.entries(this.reportData.grouped_data || {}).map(([location, lines], index) => ({
            location: location,
            lines: lines.map((line, lineIndex) => ({
                ...line,
                uniqueKey: `${location}_${lineIndex}_${line.order_reference || 'line'}` // Create unique key
            })),
            uniqueKey: `group_${index}_${location}` // Create unique key for group
        }));
        return groups;
    }
    
    /**
     * Check if there's actual transaction data to display
     */
    get hasData() {
        return this.reportData.has_data;
    }
    
    /**
     * Check if we should show the table (ALWAYS TRUE now)
     */
    get showTable() {
        return true; // Always show the table structure
    }
    
    /**
     * Get date range for display
     */
    get dateRange() {
        if (this.reportData.date_from && this.reportData.date_to) {
            return `${this.reportData.date_from} to ${this.reportData.date_to}`;
        }
        return 'No date range specified';
    }
}

// --------------------------------------------------------------------------------
// TEMPLATE AND REGISTRATION
// --------------------------------------------------------------------------------

// Updated template for detailed line report
ReportMatrixWidget.template = "sales_store_expense_report.detailed_report_template";

// Register the widget
registry.category("fields").add("report_matrix_widget", {
    component: ReportMatrixWidget,
    extractProps: ({ attrs }) => ({}), 
});