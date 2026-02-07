from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    spreadsheet_document_id = fields.Many2one(
        "documents.document",
        string="Spreadsheet Document",
        copy=False,
        readonly=True,
    )
    spreadsheet_id = fields.Many2one(
        "spreadsheet.spreadsheet",
        string="Spreadsheet",
        copy=False,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks._ensure_task_spreadsheet()
        return tasks

    def _ensure_task_spreadsheet(self):
        Document = self.env["documents.document"]
        Spreadsheet = self.env["spreadsheet.spreadsheet"]
        for task in self:
            if task.spreadsheet_document_id or task.spreadsheet_id:
                continue
            sequence_value = task.sequence or task.id
            task_name = task.name or "Task"
            spreadsheet_name = f"TASK-{sequence_value} | {task_name}"
            spreadsheet = Spreadsheet.create({"name": spreadsheet_name})
            doc_vals = {
                "name": spreadsheet_name,
                "spreadsheet_id": spreadsheet.id,
                "res_model": "project.task",
                "res_id": task.id,
            }
            if "owner_id" in Document._fields:
                doc_vals["owner_id"] = task.user_id.id or task.create_uid.id
            if "company_id" in Document._fields:
                doc_vals["company_id"] = task.company_id.id
            document = Document.create(doc_vals)
            task.write(
                {
                    "spreadsheet_document_id": document.id,
                    "spreadsheet_id": spreadsheet.id,
                }
            )

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault("spreadsheet_document_id", False)
        default.setdefault("spreadsheet_id", False)
        return super().copy(default)

    def write(self, vals):
        res = super().write(vals)
        if "active" in vals:
            for task in self:
                document = task.spreadsheet_document_id
                spreadsheet = task.spreadsheet_id
                if document and "active" in document._fields:
                    document.write({"active": vals["active"]})
                if spreadsheet and "active" in spreadsheet._fields:
                    spreadsheet.write({"active": vals["active"]})
        return res

    def unlink(self):
        documents = self.spreadsheet_document_id.exists()
        spreadsheets = self.spreadsheet_id.exists()
        res = super().unlink()
        if documents:
            documents.unlink()
        if spreadsheets:
            spreadsheets.unlink()
        return res
