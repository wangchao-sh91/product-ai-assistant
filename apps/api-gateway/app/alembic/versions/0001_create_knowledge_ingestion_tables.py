from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_knowledge_ingestion"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_uri", sa.Text()),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("system_name", sa.String(length=128)),
        sa.Column("module_name", sa.String(length=128)),
        sa.Column("environment", sa.String(length=64)),
        sa.Column("owner", sa.String(length=128)),
        sa.Column("version", sa.String(length=64)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "document_sources",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_uri", sa.Text()),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("content", sa.LargeBinary()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("doc_id", sa.String(length=64), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_chunk_id", sa.String(length=64), sa.ForeignKey("document_chunks.id", ondelete="CASCADE")),
        sa.Column("chunk_level", sa.String(length=16), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("page_no", sa.Integer()),
        sa.Column("section_title", sa.Text()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ingestion_tasks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), sa.ForeignKey("document_sources.id", ondelete="SET NULL")),
        sa.Column("document_id", sa.String(length=64), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("message", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ingestion_tasks")
    op.drop_table("document_chunks")
    op.drop_table("document_sources")
    op.drop_table("documents")
