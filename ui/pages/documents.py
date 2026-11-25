"""Document management interface with upload, polling, and deletion."""

import os

import pandas as pd
import streamlit as st

from ui.client import MediCareClient
from ui.config import get_app_config
from ui.state import get_user_id

# 1. Config & Client
cfg = get_app_config()
ui_cfg = cfg.get("ui", {})
backend_url = os.getenv("BACKEND_SERVICE_URL") or ui_cfg.get("backend_service_url", "")
secret_token = os.getenv("SERVICE_SECRET_KEY", None)
client = MediCareClient(base_url=backend_url, secret_token=secret_token)

# 2. Page Header
st.title(f"📁 {ui_cfg.get('my_documents_header', 'My Documents')}")
st.caption(ui_cfg.get("documents_page_caption", ""))

# 3. File Uploader Section
allowed_exts = ui_cfg.get(
    "allowed_upload_types",
    [".pdf", ".docx", ".txt", ".md", ".csv", ".html", ".htm"],
)
clean_exts = [ext.lstrip(".").lower() for ext in allowed_exts]

with st.container(border=True):
    st.markdown(ui_cfg.get("upload_section_header", "#### 📤 Upload Document"))
    col_upload, col_opts = st.columns([3, 2])
    with col_upload:
        uploaded_file = st.file_uploader(
            ui_cfg.get("upload_doc_label", "Select Document"),
            type=clean_exts,
            key="doc_page_uploader",
            help=ui_cfg.get("upload_doc_help", ""),
        )

    with col_opts:
        doc_insurer = st.text_input(
            ui_cfg.get("upload_insurer_label", "Insurer (optional)"),
            placeholder=ui_cfg.get("upload_insurer_placeholder", ""),
            key="doc_page_insurer",
        )
        doc_type = st.selectbox(
            ui_cfg.get("upload_doc_type_label", "Document Type"),
            ["policy", "bill", "discharge_summary", "prescription", "lab_report"],
            key="doc_page_type",
        )

    upload_btn = ui_cfg.get("upload_button", "📤 Ingest Document")
    if uploaded_file and st.button(
        upload_btn, key="doc_page_upload_btn", width="stretch", type="primary"
    ):
        with st.spinner(ui_cfg.get("doc_uploading_info", "")):
            try:
                bytes_data = uploaded_file.getvalue()
                res = client.upload_document(
                    file_bytes=bytes_data,
                    filename=uploaded_file.name,
                    user_id=get_user_id(),
                    insurer=doc_insurer.strip() if doc_insurer.strip() else None,
                    doc_type=doc_type,
                )
                doc_id = res.get("doc_id")
                queued_msg = ui_cfg.get("doc_queued_success", "Document queued")
                st.success(f"{queued_msg} (ID: `{doc_id[:8]}...`).")
                st.rerun()
            except Exception as e:
                st.error(f"Upload failed: {e}")

st.markdown("---")


# 4. User Documents List & Fragment Polling
@st.fragment(run_every=3)
def render_user_documents_table() -> None:
    """Render table of user documents with live polling when documents are processing."""
    user_id = get_user_id()
    try:
        user_docs = client.list_documents(user_id=user_id, scope="mine")
    except Exception:
        user_docs = []

    st.markdown(f"#### 📑 Your Uploaded Documents ({len(user_docs)})")
    if not user_docs:
        st.info(ui_cfg.get("no_user_docs_info", ""))
        return

    # Check if any document is currently processing
    any_processing = any(d.get("status") == "processing" for d in user_docs)
    if any_processing:
        st.caption(ui_cfg.get("docs_processing_info", ""))

    for doc in user_docs:
        d_id = doc.get("doc_id", "")
        fname = doc.get("filename") or doc.get("title") or "Document"
        status = doc.get("status", "unknown")
        pages = doc.get("pages", 1)
        chunks = doc.get("chunks", 0)
        insurer_name = doc.get("insurer") or "General"
        dtype = doc.get("doc_type", "policy")

        status_icon = (
            "✅ Ready"
            if status == "ready"
            else "⏳ Processing"
            if status == "processing"
            else "❌ Failed"
        )

        with st.container(border=True):
            col_info, col_action = st.columns([5, 1])
            with col_info:
                st.markdown(f"**📄 {fname}**")
                st.caption(
                    f"**Type**: `{dtype}` | **Insurer**: `{insurer_name}` | **Pages**: {pages} | **Chunks**: {chunks} | **Status**: {status_icon}"
                )
                if status == "failed" and doc.get("error"):
                    st.error(f"Error: {doc.get('error')}")
            with col_action:
                delete_label = ui_cfg.get("delete_doc_button_label", "Delete")
                if st.button("🗑️", key=f"del_page_doc_{d_id}", help=f"{delete_label} {fname}"):
                    try:
                        client.delete_document(d_id, user_id=user_id)
                        st.toast(f"Deleted '{fname}'", icon="🗑️")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Failed to delete: {err}")


render_user_documents_table()

st.markdown("---")

# 5. Read-only Curated Documents Section
curated_header = ui_cfg.get("curated_docs_expander", "📚 Curated Reference Documents")
with st.expander(curated_header, expanded=False):
    try:
        curated_docs = client.list_documents(scope="curated")
    except Exception:
        curated_docs = []

    if curated_docs:
        c_records = [
            {
                "Document Name": d.get("filename") or d.get("title"),
                "Type": d.get("doc_type", "policy"),
                "Insurer": d.get("insurer", "General"),
                "Pages": d.get("pages", 1),
                "Chunks": d.get("chunks", 0),
            }
            for d in curated_docs
        ]
        st.dataframe(pd.DataFrame(c_records), hide_index=True, width="stretch")
    else:
        st.caption(ui_cfg.get("curated_docs_caption", ""))
