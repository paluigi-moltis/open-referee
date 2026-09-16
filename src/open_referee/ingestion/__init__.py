"""Document ingestion: PDF / DOCX / LaTeX / Markdown -> canonical Document.

Every paragraph-level block gets a stable ``block_id`` and a SHA-256 content
hash so review comments can anchor to exact text. Figures are extracted as
images for the vision role.
"""

from open_referee.ingestion.document import Block, BlockType, Document, Figure, Section
from open_referee.ingestion.readers import ingest_document

__all__ = ["Block", "BlockType", "Document", "Figure", "Section", "ingest_document"]
