Place your tracked LaTeX sources here for Cloud Run (Docker copies this folder to `/app/templates`):

- `foodbridge_certificate.tex` — FSSAI certificate (`certificate_service`)
- `csr.tex` — CSR report (`csr_report_service`)

Local development may still use copies at the repo root instead; `get_latex_template_root()` prefers `backend/templates/` when `foodbridge_certificate.tex` exists here.

If these files are missing, PDF generation fails at runtime—add your templates before building the API image.
