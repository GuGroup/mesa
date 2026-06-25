# OpenAI File Input Notes

Use these notes when modifying the bundled API script or deciding whether a PDF can be sent directly to the model.

- Prefer the Responses API for PDF input.
- Send local PDFs as an `input_file` item with `filename` and `file_data` containing a `data:application/pdf;base64,...` value.
- The Files API path is also valid: upload the PDF with `purpose="user_data"` and pass the resulting `file_id` as an `input_file`.
- Keep individual files and combined request files under 50 MB.
- PDF parsing can include extracted text plus page images, so token use may be higher than plain text extraction.
- Use a vision-capable model for PDFs that require page-image interpretation. OpenAI's file-input guide says PDF parsing with text and page images requires models with vision capabilities.

Primary reference checked on 2026-06-23: https://developers.openai.com/api/docs/guides/file-inputs
