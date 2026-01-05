from odoo import models, fields, tools

class AnalyticReportView(models.Model):
    _name = 'analytic.report.view'
    _description = 'Analytic Report View'
    _auto = False
    _rec_name = 'account_id'
    _check_company_auto = True

    date = fields.Date(string="Date", readonly=True)
    account_id = fields.Many2one('account.analytic.account', string="Plan 1", readonly=True)
    analytic_plan_id = fields.Many2one('account.analytic.plan', string="Analytic Plan", readonly=True)
    general_account_id = fields.Many2one('account.account', string="Account", readonly=True)
    partner_id = fields.Many2one('res.partner', string="Partner", readonly=True)
    journal_id = fields.Many2one('account.journal', string="Journal", readonly=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True)
    move_id = fields.Many2one('account.move', string="Journal Entry", readonly=True)
    move_type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
        ('out_refund', 'Customer Credit Note'),
        ('in_refund', 'Vendor Refund')
    ], string="Move Type", readonly=True)
    move_state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted')
    ], string="State", readonly=True)
    debit = fields.Float(string="Debit", readonly=True)
    credit = fields.Float(string="Credit", readonly=True)
    amount = fields.Float(string="Profit", readonly=True)
    all_plans = fields.Char(string="All Plans", readonly=True)
    product_id = fields.Many2one('product.product', string="Product", readonly=True)
    plan_code = fields.Char(string="Reference", readonly=True)
    plan_name = fields.Char(string="Plan Name", readonly=True)
    move_line_name = fields.Char(string="Label", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)

        aal_model = self.env['account.analytic.line']
        plan_fields = ['account_id']
        for field_name, field in aal_model._fields.items():
            if field_name.startswith('x_plan') and field.type == 'many2one' and field.comodel_name == 'account.analytic.account':
                plan_fields.append(field_name)

        joins = []
        for f in plan_fields:
            alias = f'aaa_{f}'
            joins.append(f"LEFT JOIN account_analytic_account {alias} ON {alias}.id = aal.{f}")

        coalesce_fields = ', '.join([f'aal.{field}' for field in plan_fields])
        joins.append(f"LEFT JOIN account_analytic_account first_aaa ON first_aaa.id = COALESCE({coalesce_fields})")

        # name_selects = [
        #     f"CASE "
        #     f"WHEN {table_alias}.code IS NOT NULL AND {table_alias}.name IS NOT NULL "
        #     f"THEN '[' || {table_alias}.code || '] ' || ({table_alias}.name ->> 'en_US') "
        #     f"WHEN {table_alias}.name IS NOT NULL "
        #     f"THEN {table_alias}.name ->> 'en_US' "
        #     f"ELSE {table_alias}.code END"
        #     for table_alias in [f"aaa_{f}" for f in plan_fields]
        # ]

        name_selects = [
            f"CASE "
            f"WHEN {table_alias}.code IS NOT NULL AND {table_alias}.name IS NOT NULL "
            f"THEN ({table_alias}.name ->> 'en_US') || '   -   ' || {table_alias}.code "
            f"WHEN {table_alias}.name IS NOT NULL "
            f"THEN {table_alias}.name ->> 'en_US' "
            f"ELSE {table_alias}.code END"
            for table_alias in [f"aaa_{f}" for f in plan_fields]
        ]

        all_plans_sql = f"array_to_string(array_remove(ARRAY[{', '.join(name_selects)}], NULL), ' / ')"
        joins_sql = ' '.join(joins)

        query = f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    aal.id,
                    aal.date,
                    aal.account_id,
                    first_aaa.plan_id as analytic_plan_id,
                    aal.general_account_id,
                    aal.partner_id,
                    am.journal_id,
                    am.company_id,
                    aml.product_id,   
                    am.id as move_id,
                    am.move_type,
                    aml.name as move_line_name,  
                    am.state as move_state,
                    {all_plans_sql} as all_plans,
                    first_aaa.code as plan_code,
                    first_aaa.name ->> 'en_US' as plan_name,
                    CASE WHEN aal.amount < 0 THEN -aal.amount ELSE 0 END as debit,
                    CASE WHEN aal.amount > 0 THEN aal.amount ELSE 0 END as credit,
                    aal.amount as amount
                FROM account_analytic_line aal
                JOIN account_move_line aml ON aal.move_line_id = aml.id
                JOIN account_move am ON aml.move_id = am.id
                {joins_sql}
                WHERE am.move_type IN ('out_invoice','in_invoice','out_refund','in_refund')
            )
        """
        self.env.cr.execute(query)