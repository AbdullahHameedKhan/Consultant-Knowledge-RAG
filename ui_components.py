"""Reusable Streamlit UI components — keeps app.py under 150 lines."""
from pathlib import Path
from typing import Any

import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"


# ── Sidebar ────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.title("🗂 Knowledge Base")
        _render_kb_status()
        st.divider()
        _render_ingest_controls()
        st.divider()
        _render_settings_panel()


def _render_kb_status() -> None:
    try:
        resp = requests.get(f"{API_BASE}/status", timeout=5)
        if resp.ok:
            data = resp.json()
            col1, col2 = st.columns(2)
            col1.metric("Vectors", data.get("total_vectors", 0))
            col2.metric("Model", data.get("llm_model", "—").split(":")[0])
            st.caption(f"📁 `{data.get('document_dir', '')}` · Embed: `{data.get('embed_model', '')}`")
        else:
            st.warning("Could not reach API.")
    except requests.exceptions.ConnectionError:
        st.error("⚠️ API offline — start FastAPI first.")


def _render_ingest_controls() -> None:
    st.subheader("Ingestion")
    force = st.checkbox("Force re-embed all docs", value=False)

    uploaded_files = st.file_uploader(
        "Upload reports (.pdf, .docx, .txt)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        batch_signature = "|".join(
            sorted(f"{f.name}:{f.size}" for f in uploaded_files)
        )
        if st.session_state.get("uploaded_batch_signature") != batch_signature:
            with st.spinner("Uploading files and embedding documents…"):
                try:
                    status_resp = requests.get(f"{API_BASE}/status", timeout=10)
                    if not status_resp.ok:
                        st.error("Could not fetch document directory from API status.")
                    else:
                        document_dir = status_resp.json().get("document_dir", "")
                        if not document_dir:
                            st.error("API returned empty document directory.")
                        else:
                            target_dir = Path(document_dir)
                            target_dir.mkdir(parents=True, exist_ok=True)
                            for upload in uploaded_files:
                                target_path = target_dir / Path(upload.name).name
                                target_path.write_bytes(upload.getvalue())

                            ingest_resp = requests.post(
                                f"{API_BASE}/ingest",
                                json={"force_reload": False},
                                timeout=300,
                            )
                            if ingest_resp.ok:
                                d = ingest_resp.json()
                                st.success(
                                    f"✅ Uploaded {len(uploaded_files)} file(s) · "
                                    f"{d['chunks_added']} chunks · "
                                    f"{d['total_vectors']} total vectors"
                                )
                                st.session_state["uploaded_batch_signature"] = batch_signature
                            else:
                                st.error(f"Auto-ingest failed: {ingest_resp.text}")
                except requests.exceptions.ConnectionError:
                    st.error("API not reachable.")

    if st.button("🔄 Ingest Documents", use_container_width=True):
        with st.spinner("Embedding documents…"):
            try:
                resp = requests.post(
                    f"{API_BASE}/ingest",
                    json={"force_reload": force},
                    timeout=300,
                )
                if resp.ok:
                    d = resp.json()
                    st.success(
                        f"✅ {d['files_processed']} file(s) · "
                        f"{d['chunks_added']} chunks · "
                        f"{d['total_vectors']} total vectors"
                    )
                else:
                    st.error(f"Ingestion failed: {resp.text}")
            except requests.exceptions.ConnectionError:
                st.error("API not reachable.")


def _render_settings_panel() -> None:
    st.subheader("Settings")
    st.slider("Top-K results", min_value=1, max_value=8, value=4, key="top_k")


# ── Chat message rendering ─────────────────────────────────────────────────

def render_chat_message(role: str, content: str) -> None:
    with st.chat_message(role):
        st.markdown(content)


def render_answer_with_sources(data: dict[str, Any]) -> None:
    with st.chat_message("assistant"):
        st.markdown(data["answer"])
        render_sources_and_feedback(data)


def render_sources_and_feedback(data: dict[str, Any]) -> None:
    _render_source_expander(data.get("sources", []))
    _render_feedback_buttons(data)


def _render_source_expander(sources: list[dict]) -> None:
    if not sources:
        return
    with st.expander(f"📄 Source Context ({len(sources)} chunk(s))", expanded=False):
        for i, src in enumerate(sources, 1):
            score_pct = int(src.get("relevance_score", 0) * 100)
            st.markdown(
                f"**[{i}] {src['source_file']}** · {src['page_label']} "
                f"· Relevance: `{score_pct}%`"
            )
            st.caption(src.get("excerpt", ""))
            if i < len(sources):
                st.divider()


def _render_feedback_buttons(data: dict[str, Any]) -> None:
    cols = st.columns([1, 1, 8])
    if cols[0].button("👍", key=f"up_{hash(data['answer'][:50])}", help="Helpful"):
        _post_feedback(data, rating=2)
    if cols[1].button("👎", key=f"dn_{hash(data['answer'][:50])}", help="Not helpful"):
        _post_feedback(data, rating=1)


def _post_feedback(data: dict[str, Any], rating: int) -> None:
    try:
        requests.post(
            f"{API_BASE}/feedback",
            json={
                "question": st.session_state.get("last_question", ""),
                "answer": data["answer"],
                "rating": rating,
            },
            timeout=5,
        )
        st.toast("Thanks for the feedback!" if rating == 2 else "Noted — we'll improve.", icon="✅")
    except Exception:
        pass
